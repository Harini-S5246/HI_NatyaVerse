# HI-Natya Verse

**Where Dance Becomes Story**

An AI-powered multimodal system for understanding Bharatanatyam performances
through Mudra, Bhava, Pose, Audio, Evidence and intelligent story generation.

This repository contains **only the frontend**. It renders whatever your
Python AI backend returns — it does not run any models itself, and it does
not contain mock or placeholder analysis data. Every mudra meaning, bhava
label, confidence score, and story sentence you see in the app comes from
your backend's API response.

---

## 1. Technology stack

- React 18 + TypeScript
- Vite
- Tailwind CSS
- React Router
- Axios
- lucide-react icons

## 2. Installation

```bash
npm install
```

## 3. Environment setup

Copy the example environment file and point it at your backend:

```bash
cp .env.example .env
```

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Change this to wherever your Python backend actually runs (e.g. a different
port, or a deployed URL). Every request the frontend makes goes through
`src/services/api.ts`, which reads this variable — nothing is hardcoded in
components.

## 4. Run the dev server

```bash
npm run dev
```

The app will be available at `http://localhost:5173`. Start your Python
backend separately (in another terminal) so the two can talk to each other.

## 5. Production build

```bash
npm run build
npm run preview   # optional: preview the production build locally
```

---

## 6. Expected backend API

The frontend was built against this architecture. The exact routes will
likely evolve as you build the backend — when they do, only
`src/services/api.ts` needs to change; no component makes a direct
fetch/axios call.

| Function | Method & path | Purpose |
|---|---|---|
| `uploadPerformance(file)` | `POST /api/analyze` (multipart `video` field) | Upload a video and start analysis. Returns `{ analysis_id }`. |
| `getAnalysisStatus(id)` | `GET /api/analysis/{id}/status` | Lightweight polling endpoint used by the processing screen. |
| `getAnalysisResult(id)` | `GET /api/analysis/{id}/result` | Full multimodal result: mudra, bhava, pose, audio, evidence. |
| `getStory(id, language)` | `GET /api/story/{id}?language=Tamil` | Story/interpretation in a given language. |
| `getMultilingualStory(id)` | `GET /api/story/{id}?all_languages=true` | All language variants at once, if your backend supports it. |

### Expected result shape (`getAnalysisResult`)

See `src/types/analysis.ts` for the full, precisely-documented TypeScript
interfaces (`AnalysisResult`, `MudraDetection`, `BhavaAnalysis`,
`PoseAnalysis`, `AudioAnalysis`, `Evidence`, `StoryInterpretation`, etc.).
Nearly every field is optional — the UI only renders what is actually
present and shows an honest "not reported" state otherwise. It never
invents a mudra meaning, confidence value, or story sentence.

A minimal example:

```json
{
  "analysis_id": "abc123",
  "performance": { "performance_name": "Varnam Excerpt", "duration_seconds": 184 },
  "mudra": {
    "detections": [
      { "name": "Hamsasya", "meaning": "Swan's beak", "grounded": true, "confidence": 0.83 },
      { "name": "Swastikam", "grounded": false, "confidence": 0.41 }
    ]
  },
  "bhava": { "dominant_emotion": "Sad", "confidence": 0.47 },
  "pose": { "primary_pose": "Varnam", "confidence": 0.71 },
  "audio": { "audio_type": "rhythmic-only", "lyrics_available": false },
  "overall_evidence_strength": 0.61,
  "evidence_level": "moderate"
}
```

If your backend already returns a structured `evidence` object (grounded /
detected / unresolved / interpreted arrays), the UI uses it directly. If
not, `src/utils/evidence.ts` derives an equivalent breakdown from the
mudra/bhava/pose/audio fields above — it never fabricates a category, it
only reorganizes what the backend already sent.

## 7. How to modify the API endpoints

All routes are defined in one place:

```ts
// src/services/api.ts
const ENDPOINTS = {
  analyze: () => '/api/analyze',
  analysis: (id: string) => `/api/analysis/${id}`,
  analysisStatus: (id: string) => `/api/analysis/${id}/status`,
  analysisResult: (id: string) => `/api/analysis/${id}/result`,
  story: (id: string) => `/api/story/${id}`,
}
```

Update the strings here — no component needs to change.

## 8. Connecting to your Python backend

```
React Frontend  →  Python Backend  →  Mudra Model
                                    →  Pose Model
                                    →  Bhava Model
                                    →  Audio / Lyrics
                                    →  Multimodal Interpretation + Grounding
                                    →  LLM Story Generation (Gemini, primary)
                                    →  Multilingual Generation
```

1. Make sure your backend has CORS enabled for `http://localhost:5173` during development.
2. Set `VITE_API_BASE_URL` in `.env` to your backend's address.
3. Implement the endpoints in the table above (or update `ENDPOINTS` to match your actual routes).
4. Never place a Gemini/OpenAI API key in this frontend — those calls belong entirely on the backend.

## 9. Project structure

```
src/
  components/
    layout/        Navbar, Footer
    home/           HeroSection, HowItWorks, FeatureCard, MultimodalSection
    upload/         VideoUploader, VideoPreview
    processing/     ProcessingStages
    analysis/       AnalysisOverview, MudraCard, MudraTable, BhavaCard,
                     PoseCard, AudioCard, ConfidenceCard
    evidence/       EvidencePanel, GroundingBadge, WhyInterpretation
    story/          StoryPanel, InterpretationPanel
    common/         EmptyState, LoadingState, ErrorMessage, SectionHeading
    LanguageSelector.tsx
  pages/            Home, Analyze, Analysis, Story, NotFound
  services/api.ts   All backend communication
  types/analysis.ts All TypeScript interfaces
  hooks/            useAnalysisPolling, useLanguage, useLastAnalysisId
  utils/            format.ts, evidence.ts, languages.ts
```

## 10. Design system

- **Surfaces:** warm ivory/parchment backgrounds, warm-white cards
- **Text:** deep charcoal/espresso
- **Accents:** muted maroon/vermilion (primary), antique gold (secondary), used sparingly
- **Type:** Fraunces (display/serif headings) + Work Sans (body/UI), with
  Noto Sans Tamil/Devanagari/Malayalam/Telugu/Kannada/Bengali loaded for
  correct multilingual rendering
- **Status colors:** grounded = green, unresolved = amber, error = muted red

All tokens live in `tailwind.config.js` and `src/index.css`.
