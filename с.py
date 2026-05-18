import io
import tokenize
from pathlib import Path
from datetime import datetime

# ============================================
# Настройки
# ============================================

# Директория, которую нужно собрать
TARGET_DIR = r"./src"

# Файл вывода
OUTPUT_FILE = "all_python_files_dump.txt"

# Какие папки игнорировать (добавлены venv/env для Python)
IGNORE_FOLDERS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".idea",
    ".vscode",
    "build",
    "dist",
    "venv",
    "env",
}

# Максимальный размер файла (в байтах)
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB


# ============================================
# Вспомогательные функции
# ============================================

import ast

def clean_python_code(source: str) -> str:
    """
    Безопасно удаляет # комментарии и многострочные строки документации (docstrings),
    используя абстрактное синтаксическое дерево (AST).
    Требует Python 3.9+.
    """
    try:
        # Парсим исходный код в дерево
        tree = ast.parse(source)
        
        # Проходим по всем узлам дерева (модули, классы, функции)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                # Если первый элемент блока — это просто строка (Docstring), удаляем её
                if (node.body and 
                    isinstance(node.body[0], ast.Expr) and 
                    isinstance(node.body[0].value, ast.Constant) and 
                    isinstance(node.body[0].value.value, str)):
                    node.body.pop(0)
                    
        # Собираем код обратно. 
        # Бонус: ast.unparse вообще не знает о существовании # комментариев, 
        # поэтому они исчезают автоматически, как и пустые строки!
        return ast.unparse(tree) + "\n"
        
    except Exception:
        # Резервный вариант (Fallback) на случай синтаксических ошибок в файле
        lines = []
        for line in source.splitlines():
            stripped = line.strip()
            # Убираем хотя бы обычные комментарии и пустые строки
            if stripped and not stripped.startswith('#'):
                lines.append(line)
        return "\n".join(lines) + "\n"

def format_separator(title: str, width: int = 80) -> str:
    """
    Красивый разделитель файла.
    """
    line = "═" * width
    return (
        f"\n{line}\n"
        f"📄 {title}\n"
        f"{line}\n\n"
    )

# ============================================
# Основная логика
# ============================================

def collect_files():
    root = Path(TARGET_DIR)

    if not root.exists():
        print(f"[ERROR] Директория не найдена: {root}")
        return

    files_written = 0

    with open(OUTPUT_FILE, "w", encoding="utf-8") as output:

        # Заголовок
        output.write(
            f"{'=' * 80}\n"
            f"PYTHON PROJECT DUMP (NO COMMENTS)\n"
            f"Generated: {datetime.now()}\n"
            f"Directory: {root.resolve()}\n"
            f"{'=' * 80}\n\n"
        )

        # Сразу ищем ТОЛЬКО файлы с расширением .py
        for path in root.rglob("*.py"):

            if not path.is_file():
                continue

            # Игнор папок
            if any(folder in path.parts for folder in IGNORE_FOLDERS):
                continue

            # Игнор больших файлов
            try:
                if path.stat().st_size > MAX_FILE_SIZE:
                    print(f"[SKIP] Too large: {path}")
                    continue
            except Exception:
                continue

            try:
                relative_path = path.relative_to(root)

                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Очищаем код от комментариев и пустых строк
                cleaned_content = clean_python_code(content)

                # Если после очистки файл не пустой — записываем его
                if cleaned_content.strip():
                    output.write(format_separator(str(relative_path)))
                    output.write(cleaned_content)
                    output.write("\n")

                    files_written += 1
                    print(f"[OK] {relative_path}")
                else:
                    print(f"[SKIP] Empty after cleaning: {relative_path}")

            except Exception as e:
                print(f"[ERROR] {path}: {e}")

    print("\n" + "=" * 80)
    print(f"Готово. Собрано файлов: {files_written}")
    print(f"Результат: {OUTPUT_FILE}")
    print("=" * 80)


# ============================================
# Запуск
# ============================================

if __name__ == "__main__":
    collect_files()