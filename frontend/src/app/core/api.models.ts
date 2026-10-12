// Miroir des schémas Pydantic du backend (backend/app/schemas.py)

export interface Opening {
  eco: string;
  name: string;
}

export interface TheoryMove {
  uci: string;
  san: string;
  games: number;
  white_wins: number;
  draws: number;
  black_wins: number;
  white_pct: number;
  draw_pct: number;
  black_pct: number;
  average_rating: number | null;
}

/** Évaluation du point de vue des Blancs */
export interface Score {
  centipawns: number | null;
  mate: number | null;
}

export interface EngineLine {
  rank: number;
  score: Score;
  pv_san: string[];
}

export interface Evaluation {
  fen: string;
  side_to_move: 'white' | 'black';
  depth: number;
  score: Score;
  best_move_uci: string | null;
  best_move_san: string | null;
  lines: EngineLine[];
  game_over: string | null;
}

export interface MovesResponse {
  fen: string;
  source: 'lichess' | 'stockfish';
  in_theory: boolean;
  database: string;
  opening: Opening | null;
  total_games: number;
  moves: TheoryMove[];
  engine: Evaluation | null;
  warning: string | null;
}

export interface OpeningRef {
  slug: string;
  name: string;
  eco: string;
  moves: string;
  fen: string;
}

export interface Passage {
  score: number;
  opening_slug: string;
  opening_name: string;
  eco: string;
  section: string;
  source: 'wikibooks' | 'wikipedia_fr';
  lang: string;
  url: string;
  text: string;
}

export interface Video {
  id: string;
  title: string;
  channel: string;
  channel_id: string;
  published_at: string;
  duration_seconds: number;
  duration: string;
  views: number;
  likes: number | null;
  language: string;
  thumbnail_url: string | null;
  watch_url: string;
  embed_url: string;
  score: number;
}

export interface VideosResponse {
  opening: string;
  opening_slug: string | null;
  status: 'ok' | 'no_results' | 'quota_exceeded' | 'unavailable';
  message: string | null;
  videos: Video[];
  fallback_search_url: string;
  cached: boolean;
  quota_units_used: number;
}

export interface VectorSearchResponse {
  query: string;
  detected_opening: OpeningRef | null;
  filtered_by_opening: boolean;
  results: Passage[];
  context: string;
  videos: VideosResponse | null;
}
