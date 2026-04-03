# Candi — Frontend

Next.js 16 frontend for the Candi interview preparation assistant.

## Stack

- **Framework**: Next.js 16 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS 4 + Radix UI
- **Icons**: Lucide React
- **Markdown**: react-markdown
- **File upload**: react-dropzone

## Development

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

The frontend expects the backend API at `http://localhost:8000`. See the root `README.md` for full setup instructions.

## Key Components

| Component | Purpose |
|---|---|
| `app/page.tsx` | Main page — chat interface + file upload |
| `ChatWindow.tsx` | Message history with auto-scroll |
| `ChatInput.tsx` | Text input + send |
| `FileUpload.tsx` | Drag-and-drop zones for resume and JD |
| `MessageBubble.tsx` | Per-message rendering with markdown |
| `ThinkingAnimation.tsx` | Real-time 7-step pipeline progress |

## Build

```bash
npm run build
npm start
```
