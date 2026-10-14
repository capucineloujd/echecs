import asyncio
import json

import chess
import httpx
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.messages import AIMessage

from app.agent.graph import build_agent_graph
from app.agent.prompts import describe_position
from app.agent.runner import stream_agent
from app.agent.tools import build_tools, format_moves
from app.api.deps import get_agent
from app.main import app
from app.schemas import Evaluation, MovesResponse, Opening, Score, TheoryMove

SPANISH = "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"


class ScriptedModel(BaseChatModel):
    """Faux LLM : renvoie les messages prévus dans l'ordre et accepte bind_tools."""

    messages: object
    seen: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        ScriptedModel.seen.append(messages)
        return ChatResult(generations=[ChatGeneration(message=next(self.messages))])


def tool_call(name, args=None, call_id="1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": call_id}])


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


def make_graph(responses, analysis=None, max_steps=4):
    ScriptedModel.seen = []
    FakeAnalysis.calls = []
    model = ScriptedModel(messages=iter(responses))
    return build_agent_graph(model, build_tools(analysis or FakeAnalysis(), FakeStockfish()), max_steps)


async def collect(graph, fen=SPANISH, question=None):
    return [e async for e in stream_agent(graph, fen, ["e4", "e5", "Nf3", "Nc6", "Bb5"], question, 10, 4)]


async def test_agent_uses_state_fen_and_answers():
    graph = make_graph([tool_call("get_position_moves"), AIMessage(content="Joue a6, le coup le plus courant.")])
    events = await collect(graph)

    assert [e["event"] for e in events if e["event"] != "token"] == ["tool_start", "tool_end", "done"]
    # L'outil a reçu la FEN de l'état, pas une FEN recopiée par le LLM
    assert FakeAnalysis.calls == [chess.Board(SPANISH).fen()]
    assert "".join(e["text"] for e in events if e["event"] == "token") == "Joue a6, le coup le plus courant."
    assert events[-1]["tools_used"] == ["get_position_moves"]
    # Le résultat de l'outil est bien renvoyé au LLM au second tour
    assert "Ruy Lopez" in ScriptedModel.seen[1][-1].content


async def test_agent_can_check_a_candidate_move():
    graph = make_graph([
        tool_call("evaluate_position", {"move_san": "Nf6"}),
        AIMessage(content="ok"),
    ])
    await collect(graph)
    assert "Après Nf6" in ScriptedModel.seen[1][-1].content and "-3.69" in ScriptedModel.seen[1][-1].content


async def test_illegal_candidate_move_is_reported_to_the_llm():
    graph = make_graph([tool_call("evaluate_position", {"move_san": "Ke2"}), AIMessage(content="ok")])
    await collect(graph)
    assert "illégal" in ScriptedModel.seen[1][-1].content


async def test_tool_error_is_given_back_to_the_llm():
    graph = make_graph([tool_call("get_position_moves"), AIMessage(content="Lichess est indisponible.")], BrokenAnalysis())
    events = await collect(graph)
    assert any(e["event"] == "tool_end" and e["status"] == "error" for e in events)
    assert events[-1]["event"] == "done"


async def test_agent_must_conclude_after_max_steps():
    calls = [tool_call("get_position_moves", call_id=str(i)) for i in range(2)]
    graph = make_graph([*calls, AIMessage(content="Conclusion.")], max_steps=2)
    events = await collect(graph)
    assert events[-1] == {"event": "done", "tools_used": ["get_position_moves", "get_position_moves"]}


async def test_mistral_errors_become_readable_events():
    class FailingModel(ScriptedModel):
        def _generate(self, messages, *args, **kwargs):
            request = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
            raise httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))

    graph = build_agent_graph(FailingModel(messages=iter([])), build_tools(FakeAnalysis(), FakeStockfish()))
    events = await collect(graph)
    assert events == [{"event": "error", "message": "Trop de demandes au modèle Mistral : réessaie dans une minute."}]


async def test_timeout_becomes_error_event():
    class SlowModel(ScriptedModel):
        async def _agenerate(self, *args, **kwargs):
            await asyncio.sleep(5)

    graph = build_agent_graph(SlowModel(messages=iter([])), build_tools(FakeAnalysis(), FakeStockfish()))
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
    text = format_moves(response)
    assert text.startswith("Source : Stockfish") and "mat en 1 pour les Blancs" in text


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
    assert json.loads(events[-1][1].removeprefix("data: ")) == {"tools_used": []}


def test_endpoint_rejects_invalid_fen_before_streaming():
    app.dependency_overrides[get_agent] = lambda: make_graph([])
    try:
        assert TestClient(app).post("/api/v1/agent/analyze", json={"fen": "pas une fen"}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_endpoint_without_mistral_key_returns_503():
    assert TestClient(app).post("/api/v1/agent/analyze", json={"fen": SPANISH}).status_code == 503
