# SimpleChat Implementation Plan

## 1. Project Overview
Build a premium, responsive web application mimicking the ChatGPT interface using Vue 3. The application will support user authentication, real-time-like conversation flow (text, images, file attachments), and a history sidebar. Communications will be handled via a RESTful API.

## 2. Technology Stack
- **Framework**: Vue 3 (Script Setup) + Vite
- **State Management**: Pinia (for Auth & Chat History)
- **Routing**: Vue Router
- **HTTP Client**: Axios
- **Styling**: Vanilla CSS (Variables, Flexbox/Grid) with a focus on Glassmorphism and "Premium" dark aesthetic.
- **Markdown Rendering**: markdown-it (for rendering bot responses)
- **Icons**: Phosphor Icons or similar SVG library

## 3. Core Features
1.  **Authentication**: Login / Logout / Register / User Profile Management.
2.  **Chat Interface**:
    *   Prompt input (auto-expanding textarea).
    *   File/Image upload support.
    *   Rendering of user and bot messages (Markdown support).
    *   Streaming text effect (simulated or real).
3.  **Sidebar**:
    *   List of historical conversations grouped by time (Today, Yesterday, etc.).
    *   New Chat button.
    *   User profile menu at the bottom.
4.  **Responsive Design**: Collapsible sidebar for mobile views.

## 4. UI/Design System
- **Theme**: Deep space dark mode (`#0f172a`, `#1e293b`) with vibrant accent gradients (Purple/Blue/Pink).
- **Glassmorphism**: Translucent panels for sidebar and floating menus.
- **Typography**: 'Inter' or 'Outfit' for a clean, modern look.
- **Micro-interactions**: Hover effects on message bubbles, smooth transitions for sidebar.

## 5. Directory Structure
```
root/
├── src/
│   ├── assets/
│   │   ├── css/
│   │   │   ├── variables.css  # Global variables (colors, spacing)
│   │   │   ├── reset.css
│   │   │   └── base.css       # Typography, common utilities
│   │   └── images/
│   ├── components/
│   │   ├── common/            # Button, Input, Modal, Avatar
│   │   ├── layout/            # Sidebar, Header
│   │   └── chat/              # ChatWindow, MessageBubble, InputArea
│   ├── router/
│   ├── stores/                # Pinia stores (auth, chat)
│   ├── views/                 # LoginView, ChatView, SettingsView
│   ├── services/              # api.js (Axios instances)
│   └── App.vue
└── implementation_plan.md
```

## 6. Implementation Steps

### Phase 1: Foundation & Design System
1. Initialize Vue project with Vite.
2. Setup CSS variables and base aesthetics (Dark Mode).
3. configure Router and Pinia.

### Phase 2: UI Components (Stateless)
1. Build specific functional components: `ChatMessage`, `ChatInput`, `SidebarItem`.
2. Ensure "Premium" feel with animations and high-quality CSS.

### Phase 3: Core Logic & Routing
1. create `ChatView` layout (Sidebar + Main Content).
2. Implement message rendering logic (Markdown).
3. Build the `LoginView` and `RegisterView` screens.

### Phase 4: State Management & API Integration
1. **Auth Store**: Handle Login/Logout and maintain User state.
2. **Chat Store**: Methods to `sendMessage`, `uploadFile`, `fetchHistory`.
3. Connect Axios to dummy (or real) RESTful endpoints.

### Phase 5: Polish & Refinement
1. Add streaming text effect.
2. Optimize mobile responsiveness.
3. Final design review (colors, spacing, shadows).

## 7. API Contract (Draft)
- `POST /api/auth/login`
- `GET /api/conversations`
- `GET /api/conversations/:id`
- `POST /api/conversations/:id/message` (Support multipart/form-data for files)
