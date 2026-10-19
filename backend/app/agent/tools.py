from typing import TYPE_CHECKING, Annotated

import chess
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from app.rag.catalog import OpeningCatalog
from app.schemas import Evaluation, MovesResponse, Score
from app.services.position_analysis import PositionAnalysisService
from app.services.stockfish import StockfishService

if TYPE_CHECKING:
    from app.services.youtube import YouTubeService

MAX_PASSAGE_CHARS = 700
PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
GAIN_NAMES = {1: "un pion", 2: "deux pions", 3: "une pièce (Cavalier ou Fou)", 5: "une Tour", 9: "la Dame"}


def side(color: chess.Color) -> str:
    return "Blancs" if color == chess.WHITE else "Noirs"


def describe_score(score: Score) -> str:
    if score.mate is not None:
        if score.mate == 0:
            return "échec et mat"
        return f"les {'Blancs' if score.mate > 0 else 'Noirs'} matent en {abs(score.mate)} coup(s)"
    cp = score.centipawns or 0
    leader = "Blancs" if cp > 0 else "Noirs"
    if abs(cp) < 30:
        verdict = "position équilibrée"
    elif abs(cp) < 100:
        verdict = f"léger avantage aux {leader}"
    elif abs(cp) < 250:
        verdict = f"net avantage aux {leader}"
    else:
        verdict = f"avantage décisif aux {leader}"
    return f"{verdict} ({cp / 100:+.2f})"


def material(board: chess.Board) -> int:
    return sum(
        value * (len(board.pieces(piece, chess.WHITE)) - len(board.pieces(piece, chess.BLACK)))
        for piece, value in PIECE_VALUES.items()
    )


def material_outcome(board: chess.Board, pv_san: list[str]) -> str:
    end = board.copy(stack=False)
    for san in pv_san:
        end.push_san(san)
    if end.is_checkmate():
        return f"finit par l'échec et mat des {side(end.turn)}"
    delta = material(end) - material(board)
    if abs(delta) < 1:
        return "matériel égal"
    winner = "Blancs" if delta > 0 else "Noirs"
    gain = GAIN_NAMES.get(abs(delta), f"du matériel valant {abs(delta)} pions (Cavalier/Fou = 3, Tour = 5, Dame = 9)")
    return f"les {winner} gagnent {gain}"


def format_engine(board: chess.Board, evaluation: Evaluation) -> str:
    if evaluation.game_over:
        return f"Partie terminée ({evaluation.game_over})."
    lines = [
        f"Stockfish (profondeur {evaluation.depth}), {side(board.turn)} au trait : {describe_score(evaluation.score)}.",
        "Meilleures suites (le premier coup est celui à jouer) :",
    ]
    for line in evaluation.lines:
        lines.append(
            f"  {line.rank}) {' '.join(line.pv_san[:8])} : {describe_score(line.score)}, "
            f"{material_outcome(board, line.pv_san[:8])}"
        )
    mate = evaluation.score.mate
    if mate and (mate > 0) == (board.turn == chess.WHITE) and evaluation.lines:
        lines.append(f"Il y a un mat : seul le coup {evaluation.lines[0].pv_san[0]} compte.")
    return "\n".join(lines)


def french_name(catalog: OpeningCatalog | None, lichess_name: str) -> str:
    detected = catalog.detect(lichess_name) if catalog else None
    return f"{detected.name} ({lichess_name})" if detected else lichess_name


def format_moves(board: chess.Board, result: MovesResponse, catalog: OpeningCatalog | None = None) -> str:
    opening = (
        f"{french_name(catalog, result.opening.name)}, code ECO {result.opening.eco}"
        if result.opening
        else "non nommée par Lichess (reprendre le nom donné pour les coups précédents s'il y en a 1)"
    )
    if result.in_theory:
        base = "parties de maîtres" if result.database == "masters" else "parties en ligne Lichess"
        lines = [
            f"Source choisie : théorie Lichess ({base}), position connue ({result.total_games} parties).",
            f"Ouverture : {opening}.",
            f"Coup de référence : {result.moves[0].san} (le plus joué par les maîtres).",
            f"Coups joués par les {side(board.turn)} dans cette position, du plus fréquent au moins fréquent :",
        ]
        for move in result.moves[:5]:
            share = round(100 * move.games / result.total_games) if result.total_games else 0
            own = move.white_pct if board.turn == chess.WHITE else move.black_pct
            other = move.black_pct if board.turn == chess.WHITE else move.white_pct
            lines.append(
                f"  {move.san} : joué dans {share} % des parties ; ensuite les {side(board.turn)} gagnent {own} %, "
                f"nulles {move.draw_pct} %, les {side(not board.turn)} gagnent {other} %"
            )
        lines.append("Le coup le plus fréquent est la référence ; des pourcentages proches sont normaux en ouverture")
        return "\n".join(lines)
    reason = result.warning or f"position sortie de la théorie (seulement {result.total_games} parties connues)"
    engine = format_engine(board, result.engine) if result.engine else "Évaluation indisponible."
    best = result.engine.best_move_san if result.engine else None
    reference = f"Coup de référence : {best} (meilleur coup selon Stockfish).\n" if best else ""
    return f"Source choisie : Stockfish, {reason}.\nOuverture : {opening}.\n{reference}{engine}"


def build_tools(
    analysis: PositionAnalysisService,
    stockfish: StockfishService,
    rag_graph=None,
    youtube: "YouTubeService | None" = None,
    rag_min_score: float = 0.35,
    catalog: OpeningCatalog | None = None,
):
    @tool
    async def get_position_moves(state: Annotated[dict, InjectedState]) -> str:
        """Coups théoriques de la position actuelle (Lichess, parties de maîtres) avec le nom de l'ouverture. Si la position est sortie de la théorie, renvoie l'analyse Stockfish à la place."""
        board = chess.Board(state["fen"])
        return format_moves(board, await analysis.analyze(board), catalog)

    @tool
    async def evaluate_position(state: Annotated[dict, InjectedState], move_san: str | None = None) -> str:
        """Évaluation Stockfish de la position actuelle, ou de la position après le coup `move_san` (notation anglaise, ex. "Nxd5") pour vérifier un coup précis."""
        board = chess.Board(state["fen"])
        prefix = ""
        if move_san:
            try:
                board.push_san(move_san)
            except ValueError:
                return f"Le coup {move_san} est illégal dans cette position."
            prefix = (
                f"Coup testé : {move_san} des {side(not board.turn)} (coup hypothétique, pas encore joué). "
                f"Ensuite c'est aux {side(board.turn)} de jouer.\n"
            )
        return prefix + format_engine(board, await stockfish.evaluate(board))

    @tool
    async def search_opening_knowledge(query: str) -> str:
        """Recherche dans les articles Wikibooks / Wikipédia sur les ouvertures . `query` doit contenir le nom de l'ouverture."""
        if rag_graph is None:
            return "Base documentaire indisponible."
        state = await rag_graph.ainvoke(
            {"query": query, "opening": None, "top_k": 3, "min_score": rag_min_score, "include_videos": False}
        )
        if not state["results"]:
            return "Aucun passage pertinent trouvé."
        return "\n\n".join(
            f"[{r['source']}, {r['opening_name']}, {r['section']}]\n{r['text'][:MAX_PASSAGE_CHARS]}"
            for r in state["results"]
        )

    @tool
    async def find_videos(opening: str) -> str:
        """Vidéos YouTube pédagogiques sur une ouverture . Consomme du quota : à n'utiliser que si l'élève veut des vidéos."""
        if youtube is None:
            return "Recherche de vidéos indisponible."
        result = await youtube.find_videos(opening)
        if not result.videos:
            return result.message or "Aucune vidéo trouvée."
        return "\n".join(f"- {v.title} ({v.channel}, {v.duration}) : {v.watch_url}" for v in result.videos[:3])

    return [get_position_moves, evaluate_position, search_opening_knowledge, find_videos]
