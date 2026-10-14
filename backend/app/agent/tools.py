"""Outils de l'agent. La FEN vient de l'état du graphe (InjectedState) et non des arguments
du LLM : il ne peut pas la recopier de travers."""

from typing import TYPE_CHECKING, Annotated

import chess
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from app.schemas import Evaluation, MovesResponse, Score
from app.services.position_analysis import PositionAnalysisService
from app.services.stockfish import StockfishService

if TYPE_CHECKING:
    from app.services.youtube import YouTubeService

MAX_PASSAGE_CHARS = 700


def format_score(score: Score) -> str:
    if score.mate is not None:
        return f"mat en {abs(score.mate)} pour les {'Blancs' if score.mate > 0 else 'Noirs'}"
    return f"{(score.centipawns or 0) / 100:+.2f}"


def format_engine(evaluation: Evaluation) -> str:
    if evaluation.game_over:
        return f"Partie terminée ({evaluation.game_over})."
    lines = [f"Évaluation Stockfish (profondeur {evaluation.depth}) : {format_score(evaluation.score)}"]
    for line in evaluation.lines:
        lines.append(f"  {line.rank}) {' '.join(line.pv_san[:6])} ({format_score(line.score)})")
    return "\n".join(lines)


def format_moves(result: MovesResponse) -> str:
    opening = f"{result.opening.eco} {result.opening.name}" if result.opening else "non nommée par Lichess"
    if result.in_theory:
        base = "parties de maîtres" if result.database == "masters" else "parties en ligne Lichess"
        lines = [f"Source : Lichess ({base}), {result.total_games} parties. Ouverture : {opening}.", "Coups joués :"]
        for move in result.moves[:5]:
            share = round(100 * move.games / result.total_games) if result.total_games else 0
            lines.append(
                f"  {move.san} : {share} % des parties (Blancs gagnent {move.white_pct} %, "
                f"nulles {move.draw_pct} %, Noirs gagnent {move.black_pct} %)"
            )
        return "\n".join(lines)
    reason = result.warning or f"position hors théorie ({result.total_games} parties connues)"
    engine = format_engine(result.engine) if result.engine else "Évaluation indisponible."
    return f"Source : Stockfish, {reason}. Ouverture : {opening}.\n{engine}"


def build_tools(
    analysis: PositionAnalysisService,
    stockfish: StockfishService,
    rag_graph=None,
    youtube: "YouTubeService | None" = None,
    rag_min_score: float = 0.35,
):
    @tool
    async def get_position_moves(state: Annotated[dict, InjectedState]) -> str:
        """Coups théoriques de la position actuelle (Lichess, parties de maîtres) avec le nom de
        l'ouverture. Si la position est sortie de la théorie, renvoie l'analyse Stockfish à la place."""
        return format_moves(await analysis.analyze(chess.Board(state["fen"])))

    @tool
    async def evaluate_position(state: Annotated[dict, InjectedState], move_san: str | None = None) -> str:
        """Évaluation Stockfish de la position actuelle, ou de la position après le coup `move_san`
        (notation anglaise, ex. "Nxd5") pour vérifier un coup précis."""
        board = chess.Board(state["fen"])
        prefix = ""
        if move_san:
            try:
                board.push_san(move_san)
            except ValueError:
                return f"Le coup {move_san} est illégal dans cette position."
            prefix = f"Après {move_san} : "
        return prefix + format_engine(await stockfish.evaluate(board))

    @tool
    async def search_opening_knowledge(query: str) -> str:
        """Recherche dans les articles Wikibooks / Wikipédia sur les ouvertures (idées, plans,
        pièges, histoire). `query` doit contenir le nom de l'ouverture, ex. "plans de la partie espagnole"."""
        if rag_graph is None:
            return "Base documentaire indisponible."
        state = await rag_graph.ainvoke(
            {"query": query, "opening": None, "top_k": 3, "min_score": rag_min_score, "include_videos": False}
        )
        if not state["results"]:
            return "Aucun passage pertinent trouvé."
        return "\n\n".join(
            f"[{r['source']} — {r['opening_name']} — {r['section']}]\n{r['text'][:MAX_PASSAGE_CHARS]}"
            for r in state["results"]
        )

    @tool
    async def find_videos(opening: str) -> str:
        """Vidéos YouTube pédagogiques sur une ouverture (nom de l'ouverture, ex. "Défense sicilienne").
        Consomme du quota : à n'utiliser que si l'élève veut des vidéos."""
        if youtube is None:
            return "Recherche de vidéos indisponible."
        result = await youtube.find_videos(opening)
        if not result.videos:
            return result.message or "Aucune vidéo trouvée."
        return "\n".join(f"- {v.title} ({v.channel}, {v.duration}) : {v.watch_url}" for v in result.videos[:3])

    return [get_position_moves, evaluate_position, search_opening_knowledge, find_videos]
