"""
Базовий клас Project.

Кожен MCP-проєкт (worqen, codehive, worqen_api, ...) реалізує цей інтерфейс.
Сервер у server.py не знає деталей про конкретні проєкти — він просто
проходиться по реєстру PROJECTS і питає кожен "це твій tool?".
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional

from mcp.types import Tool, TextContent


class Project(ABC):
    """
    Базовий клас для MCP-проєкту.

    Підкласи мають визначити:
      - name: коротке ім'я проєкту (для логів і помилок)
      - tools(): список MCP Tool() цього проєкту
      - try_dispatch(): спроба обробити виклик; None якщо tool не наш
    """

    name: str

    @abstractmethod
    def tools(self) -> list[Tool]:
        """Список Tool() які реєструє цей проєкт."""

    @abstractmethod
    def try_dispatch(
        self,
        tool_name: str,
        args: dict,
        format_response: Callable[[object], list[TextContent]],
    ) -> Optional[list[TextContent]]:
        """
        Спроба обробити виклик tool_name з args.

        Повертає:
            list[TextContent] — якщо tool належить цьому проєкту і виконаний
            None              — якщо tool НЕ належить цьому проєкту
                                (сервер далі питатиме наступні проєкти)

        format_response — helper з server.py: приймає dict/list, повертає
        список TextContent у форматі MCP. Передається через параметр щоб
        не плодити циклічних імпортів проєкт ↔ server.
        """
