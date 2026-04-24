# 💌 AI Email Assistant - Backend

Hey there! Welcome to the **Backend API** for the AI Email Assistant project. 👋

This is the brain behind the magic! It powers the email drafting, summarization, and management features using intelligent agents. It connects with Gmail, processes data using AI, and securely serves the frontend application. 

## 🚀 Live Demo

You can check out the live frontend project that this backend powers here: **[AI Email Assistant Live](https://ai-email.dhakalnirajan.com.np/)**

## 🎥 Watch How It Works

Curious about how it all fits together? Here's a quick demo video showing the full project in action:

[![AI Email Assistant Demo Video](https://img.youtube.com/vi/ZkKSU_7UJYc/maxresdefault.jpg)](https://www.youtube.com/watch?v=ZkKSU_7UJYc)

---

## 🛠️ Getting Started Locally

If you'd like to run this backend on your own machine, follow these steps.

### Prerequisites

Make sure you have Python 3.13+ installed and a package manager like `uv` or `pip`.

### Installation

1. Clone the repository and navigate to the project directory.
2. Install the dependencies.

Using `uv` (recommended):
```bash
uv sync
```
*Or using pip:*
```bash
pip install .
```

3. Set up your environment variables by copying `.env.example` to `.env` and filling in your required API keys (OpenAI, Supabase, Google credentials, etc.).

4. Run the development server:

```bash
uvicorn main:app --reload
```

5. The API will be available at `http://localhost:8000`. You can explore the interactive API documentation at `http://localhost:8000/docs`!

---

## 💡 Tech Stack

This backend is built for speed and intelligence using:
- [FastAPI](https://fastapi.tiangolo.com/) - Lightning-fast web framework
- [LangChain](https://www.langchain.com/) & [LangGraph](https://langchain-ai.github.io/langgraph/) - For building intelligent, stateful AI agents
- [Supabase](https://supabase.com/) - Authentication and database
- [PostgreSQL](https://www.postgresql.org/) - Relational database 

*Feel free to explore the code, suggest improvements, or build your own cool features on top of it!* 😄
