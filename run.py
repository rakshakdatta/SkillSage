"""Start the SkillSage development server:  python run.py"""
from app import create_app
from app.config import Settings

settings = Settings.from_env()
app = create_app(settings)

if __name__ == "__main__":
    # 127.0.0.1 only: this is a development server. Use a real WSGI server to deploy.
    app.run(host="127.0.0.1", port=settings.port, debug=False)