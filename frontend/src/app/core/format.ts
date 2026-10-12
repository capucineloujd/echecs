import { Score } from './api.models';

/** "+0.35", "-1.20", "#3" (mat en 3 pour les Blancs), "#-2" */
export function formatScore(score: Score): string {
  if (score.mate !== null && score.mate !== undefined) return `#${score.mate}`;
  const pawns = (score.centipawns ?? 0) / 100;
  return `${pawns > 0 ? '+' : ''}${pawns.toFixed(2)}`;
}

/** Phrase compréhensible par un jeune joueur */
export function describeScore(score: Score): string {
  if (score.mate !== null && score.mate !== undefined) {
    if (score.mate === 0) return 'Échec et mat';
    return `${score.mate > 0 ? 'Les Blancs' : 'Les Noirs'} peuvent mater en ${Math.abs(score.mate)}`;
  }
  const cp = score.centipawns ?? 0;
  const side = cp > 0 ? 'Blancs' : 'Noirs';
  if (Math.abs(cp) < 30) return 'Position équilibrée';
  if (Math.abs(cp) < 100) return `Léger avantage aux ${side}`;
  if (Math.abs(cp) < 250) return `Net avantage aux ${side}`;
  return `Avantage décisif aux ${side}`;
}

/** Part de la barre d'évaluation côté Blancs, entre 0 et 100 */
export function whiteShare(score: Score): number {
  if (score.mate !== null && score.mate !== undefined) return score.mate > 0 ? 100 : score.mate < 0 ? 0 : 50;
  const cp = score.centipawns ?? 0;
  return 50 + 50 * (2 / (1 + Math.exp(-0.004 * cp)) - 1);
}

export function compactNumber(n: number): string {
  return new Intl.NumberFormat('fr-FR', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
}
