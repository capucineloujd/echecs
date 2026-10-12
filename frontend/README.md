# Frontend — Coach d'ouvertures

Application Angular 22 (composants standalone, signals, sans zone.js).
Voir le README à la racine du projet pour l'architecture et le lancement avec Docker.

```bash
npm ci
npm start          # http://localhost:4200, /api redirigé vers http://localhost:8000 (proxy.conf.json)
npm test           # tests unitaires (Vitest)
npm run build      # build de production dans dist/frontend/browser
```
