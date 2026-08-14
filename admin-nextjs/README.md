# FixPro Admin — Dashboard Next.js

Tableau de bord administrateur pour FixPro Guinee.

## Stack

- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Donnees mock en V1 (base de donnees en V2)

## Prerequis

- Node.js 18+
- npm ou pnpm

## Installation

```bash
cd admin-nextjs
npm install
```

## Lancer en local

```bash
npm run dev
```

Ouvrir <http://localhost:3000/admin>

## Build

```bash
npm run build
```

## Deploiement Vercel

1. Connecter le dossier `admin-nextjs` a Vercel.
2. Framework preset : Next.js
3. Build command : `npm run build`
4. Output directory : `dist`
5. Ajouter les variables d'environnement selon `env.example`.

## Auteur

FixPro Guinee
