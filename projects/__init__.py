"""
Реєстр MCP-проєктів.

Сервер у server.py не знає деталей про конкретні проєкти — він просто
проходить по цьому списку, питає кожен .tools() для list_tools і
.try_dispatch() для call_tool. Перший проєкт що повернув не-None
обслужив виклик.

Щоб додати новий проєкт:
  1. Створи projects/<name>/project.py з класом <Name>Project(Project)
  2. Імпортуй сюди
  3. Додай інстанцію у PROJECTS
"""

from projects.base import Project
from projects.worqen.project import WorqenProject
from projects.codehive.project import CodehiveProject
from projects.worqen_api.project import WorqenApiProject


PROJECTS: list[Project] = [
    WorqenProject(),
    CodehiveProject(),
    WorqenApiProject(),
]
