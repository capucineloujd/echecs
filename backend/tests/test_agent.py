import asyncio
import json
import chess
import httpx
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from app.agent.graph import Decision, build_agent_graph
from app.agent.prompts import describe_position
from app.agent.runner import stream_agent
from app.agent.tools import build_tools, format_engine, format_moves, material_outcome
from app.rag.catalog import OpeningCatalog
from app.api.deps import get_agent
from app.main import app

from app.schemas import EngineLine, Evaluation, MovesResponse, Opening, Score, TheoryMove

SPANISH = "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"




class ScriptedModel(BaseChatModel):
    messages: object
    decisions: object = iter([])
    seen: list = []
    decision_inputs: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def with_structured_output(self, schema, **kwargs):
        async def decide(messages):
            ScriptedModel.decision_inputs.append(messages)
            return next(self.decisions)

        return RunnableLambda(decide)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        ScriptedModel.seen.append(messages)
        return ChatResult(generations=[ChatGeneration(message=next(self.messages))])


def decision(tool, argument=None):
    return Decision(reason="test", tool=tool, argument=argument)


class FakeAnalysis:
    calls: list = []

    async def analyze(self, board, database=None):
        FakeAnalysis.calls.append(board.fen())
        return MovesResponse(
            fen=board.fen(), source="lichess", in_theory=True, database="masters", total_games=1000,
            opening=Opening(eco="C60", name="Ruy Lopez"),
            moves=[TheoryMove(uci="a7a6", san="a6", games=700, white_wins=300, draws=300, black_wins=100,
                              white_pct=43, draw_pct=43, black_pct=14)],
        )


class FakeStockfish:
    async def evaluate(self, board, depth=None, multipv=None):
        return Evaluation(fen=board.fen(), side_to_move="white", depth=18, score=Score(centipawns=-369),
                          best_move_uci=None, best_move_san=None, lines=[])


class BrokenAnalysis:
    async def analyze(self, board, database=None):
        raise RuntimeError("Lichess en panne")


def make_graph(responses, decisions=(), analysis=None, max_steps=4):
    ScriptedModel.seen = []
    ScriptedModel.decision_inputs = []
    FakeAnalysis.calls = []
    model = ScriptedModel(messages=iter(responses), decisions=iter([*decisions, decision("answer")]))
    tools = build_tools(analysis or FakeAnalysis(), FakeStockfish(), catalog=OpeningCatalog.load())
    return build_agent_graph(model, tools, max_steps)


async def collect(graph, fen=SPANISH, question=None):
    return [e async for e in stream_agent(graph, fen, ["e4", "e5", "Nf3", "Nc6", "Bb5"], question, 10, 4)]


async def test_position_is_always_read_before_the_llm_answers():
    graph = make_graph([AIMessage(content="Joue a6, le coup le plus courant.")])
    events = await collect(graph)

    assert [e["event"] for e in events if e["event"] != "token"] == ["tool_start", "tool_end", "done"]
    assert FakeAnalysis.calls == [chess.Board(SPANISH).fen()]
    assert "".join(e["text"] for e in events if e["event"] == "token") == "Joue a6, le coup le plus courant."
    assert events[-1]["tools_used"] == ["get_position_moves"]
    assert "Partie espagnole (Ruy Lopez)" in ScriptedModel.decision_inputs[0][-1].content


async def test_answer_ends_with_a_reminder_of_the_established_facts():
    graph = make_graph([AIMessage(content="ok")])
    await collect(graph, question="Que jouer ?")
    reminder = ScriptedModel.seen[0][-1].content
    assert "Coup de référence : a6" in reminder
    assert "dans la théorie" in reminder and "Question de l'élève : Que jouer ?" in reminder


async def test_agent_checks_a_candidate_move_it_chose():
    graph = make_graph([AIMessage(content="ok")], [decision("evaluate_position", "Nf6")])
    events = await collect(graph)
    assert events[-1]["tools_used"] == ["get_position_moves", "evaluate_position"]
    result = ScriptedModel.decision_inputs[1][-1].content
    assert "Coup testé : Nf6 des Noirs" in result and "avantage décisif aux Noirs (-3.69)" in result


async def test_illegal_candidate_move_is_reported_to_the_llm():
    graph = make_graph([AIMessage(content="ok")], [decision("evaluate_position", "Ke2")])
    await collect(graph)
    assert "illégal" in ScriptedModel.decision_inputs[1][-1].content


async def test_tool_error_is_given_back_to_the_llm():
    graph = make_graph([AIMessage(content="Lichess est indisponible.")], analysis=BrokenAnalysis())
    events = await collect(graph)
    assert any(e["event"] == "tool_end" and e["status"] == "error" for e in events)
    assert events[-1]["event"] == "done"


async def test_same_tool_twice_goes_straight_to_the_answer():
    repeated = [decision("evaluate_position", "Nf6"), decision("evaluate_position", "Nf6")]
    graph = make_graph([AIMessage(content="ok")], repeated)
    events = await collect(graph)
    assert events[-1]["tools_used"] == ["get_position_moves", "evaluate_position"]


async def test_unreadable_decision_falls_back_to_answering():
    from langchain_core.exceptions import OutputParserException

    class Confused(ScriptedModel):
        def with_structured_output(self, schema, **kwargs):
            async def decide(messages):
                raise OutputParserException("JSON invalide")

            return RunnableLambda(decide)

    model = Confused(messages=iter([AIMessage(content="Joue a6.")]))
    graph = build_agent_graph(model, build_tools(FakeAnalysis(), FakeStockfish()))
    events = await collect(graph)
    assert events[-1]["event"] == "done"
    assert "".join(e["text"] for e in events if e["event"] == "token") == "Joue a6."


async def test_agent_must_conclude_after_max_steps():
    many = [decision("evaluate_position", move) for move in ("Nf6", "a6", "d6")]
    graph = make_graph([AIMessage(content="Conclusion.")], many, max_steps=2)
    events = await collect(graph)
    assert events[-1] == {
        "event": "done",
        "tools_used": ["get_position_moves", "evaluate_position", "evaluate_position"],
    }


async def test_mistral_errors_become_readable_events():
    class FailingModel(ScriptedModel):
        def _generate(self, messages, *args, **kwargs):
            request = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
            raise httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))

    graph = build_agent_graph(
        FailingModel(messages=iter([]), decisions=iter([decision("answer")])), build_tools(FakeAnalysis(), FakeStockfish())
    )
    events = await collect(graph)
    assert events[-1] == {"event": "error", "message": "Trop de demandes au modèle de langage : réessaie dans une minute."}


async def test_timeout_becomes_error_event():
    class SlowModel(ScriptedModel):
        async def _agenerate(self, *args, **kwargs):
            await asyncio.sleep(5)

    graph = build_agent_graph(
        SlowModel(messages=iter([]), decisions=iter([decision("answer")])), build_tools(FakeAnalysis(), FakeStockfish())
    )
    events = [e async for e in stream_agent(graph, SPANISH, [], None, 0.05, 4)]
    assert events[-1]["event"] == "error" and "trop de temps" in events[-1]["message"]


def test_position_description_has_fen_history_and_diagram():
    text = describe_position(SPANISH, ["e4", "e5", "Nf3", "Nc6", "Bb5"], None)
    assert SPANISH in text
    assert "1.e4 e5 2.Nf3 Nc6 3.Bb5" in text
    assert "Trait aux Noirs" in text
    assert "r . b q k b n r" in text


def test_format_moves_out_of_theory_mentions_stockfish():
    response = MovesResponse(
        fen=SPANISH, source="stockfish", in_theory=False, database="masters", total_games=1,
        engine=Evaluation(fen=SPANISH, side_to_move="black", depth=18, score=Score(mate=1),
                          best_move_uci=None, best_move_san=None, lines=[]),
    )
    text = format_moves(chess.Board(SPANISH), response)
    assert text.startswith("Source choisie : Stockfish") and "les Blancs matent en 1" in text


def test_material_outcome_reveals_the_elephant_trap():
    board = chess.Board("r1bqkb1r/pppn1ppp/5n2/3N2B1/3P4/8/PP2PPPP/R2QKBNR b KQkq - 0 6")
    assert material_outcome(board, "Nxd5 Bxd8 Bb4+ Qd2 Bxd2+ Kxd2 Kxd8".split()) == (
        "les Noirs gagnent une pièce (Cavalier ou Fou)"
    )


def test_mate_is_singled_out():
    board = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
    evaluation = Evaluation(
        fen=board.fen(), side_to_move="white", depth=18, score=Score(mate=1), best_move_uci="h5f7",
        best_move_san="Qxf7#", lines=[EngineLine(rank=1, score=Score(mate=1), pv_san=["Qxf7#"])],
    )
    text = format_engine(board, evaluation)
    assert "finit par l'échec et mat des Noirs" in text
    assert "seul le coup Qxf7# compte" in text


def test_endpoint_streams_sse():
    app.dependency_overrides[get_agent] = lambda: make_graph([AIMessage(content="Bonjour")])
    try:
        with TestClient(app).stream("POST", "/api/v1/agent/analyze", json={"fen": SPANISH}) as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            body = response.read().decode()
    finally:
        app.dependency_overrides.clear()
    events = [block.split("\n") for block in body.strip().split("\n\n")]
    assert events[-1][0] == "event: done"
    assert json.loads(events[-1][1].removeprefix("data: ")) == {"tools_used": ["get_position_moves"]}


def test_endpoint_rejects_invalid_fen_before_streaming():
    app.dependency_overrides[get_agent] = lambda: make_graph([AIMessage(content="ok")])
    try:
        assert TestClient(app).post("/api/v1/agent/analyze", json={"fen": "pas une fen"}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_endpoint_without_mistral_key_returns_503():
    assert TestClient(app).post("/api/v1/agent/analyze", json={"fen": SPANISH}).status_code == 503


async def test_ollama_down_and_missing_model_are_explained():
    import ollama

    for error, expected in [
        (ConnectionError("Failed to connect to Ollama"), "Ollama est-il lancé"),
        (ollama.ResponseError("model 'qwen3:8b' not found", 404), "ollama pull"),
    ]:
        class Failing(ScriptedModel):
            def _generate(self, *args, _error=error, **kwargs):
                raise _error

        graph = build_agent_graph(
            Failing(messages=iter([]), decisions=iter([decision("answer")])), build_tools(FakeAnalysis(), FakeStockfish())
        )
        events = await collect(graph)
        assert events[-1]["event"] == "error" and expected in events[-1]["message"]


def test_unknown_provider_is_rejected():
    import pytest

    from app.agent.llm import build_chat_model
    from app.config import Settings

    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        build_chat_model(Settings(llm_provider="autre"))
    assert build_chat_model(Settings(llm_provider="mistral", mistral_api_key="")) is None
    assert build_chat_model(Settings(llm_provider="ollama")).model == "qwen3:8b"
