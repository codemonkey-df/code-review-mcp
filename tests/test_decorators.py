"""Tests for decorator, async, and JSDoc handling in section parsing."""

from pathlib import Path

from sections import parse_sections


def test_python_function_with_decorators() -> None:
    """Test that decorators are included in function sections."""
    content = """
import os

@app.route('/users')
@require_auth
def get_users():
    return []
"""
    sections = parse_sections(content.strip(), Path("test.py"))
    func_section = next(s for s in sections if s.kind == "function")
    assert func_section.name == "get_users"
    assert "@app.route('/users')" in func_section.text
    assert "@require_auth" in func_section.text
    assert func_section.start_line == 3  # Line with @app.route


def test_python_class_with_decorators() -> None:
    """Test that class decorators are included."""
    content = """
@dataclass
@frozen
class User:
    name: str
    age: int
"""
    sections = parse_sections(content.strip(), Path("test.py"))
    class_section = sections[0]
    assert class_section.kind == "class"
    assert "@dataclass" in class_section.text
    assert "@frozen" in class_section.text
    assert class_section.start_line == 1


def test_typescript_decorators() -> None:
    """Test TypeScript decorator handling."""
    content = """
@Component({
  selector: 'app-user'
})
class UserComponent {
  constructor() {}
}
"""
    sections = parse_sections(content.strip(), Path("test.ts"))

    class_section = sections[0]
    assert "@Component" in class_section.text
    assert class_section.start_line == 1


def test_jsdoc_included() -> None:
    """Test that JSDoc comments are included with functions."""
    content = """
/**
 * Fetches user data from API
 * @param {string} userId - The user ID
 * @returns {Promise<User>}
 */
async function fetchUser(userId) {
  return await api.get(userId);
}
"""
    sections = parse_sections(content.strip(), Path("test.js"))

    func_section = sections[0]
    assert "/**" in func_section.text
    assert "Fetches user data" in func_section.text
    assert "@param" in func_section.text
    assert func_section.start_line == 1


def test_multiple_decorators_with_gaps() -> None:
    """Test decorators with empty lines between them."""
    content = """
@cache

@validate_input
@log_calls

def process_data(data):
    return data
"""
    sections = parse_sections(content.strip(), Path("test.py"))

    func_section = sections[0]
    assert "@cache" in func_section.text
    assert "@validate_input" in func_section.text
    assert "@log_calls" in func_section.text


def test_python_async_def() -> None:
    """Test that async def is detected as function with correct name."""
    content = """
async def foo():
    return 1
"""
    sections = parse_sections(content.strip(), Path("test.py"))

    func_section = next(s for s in sections if s.kind == "function")
    assert func_section.name == "foo"
    assert "async def foo" in func_section.text


def test_python_async_def_with_decorators() -> None:
    """Test that async def with decorators is detected and decorators are included in section."""
    content = """
@router.get("/items")
@cache(ttl=60)
async def get_items():
    return []
"""
    sections = parse_sections(content.strip(), Path("test.py"))

    func_section = next(s for s in sections if s.kind == "function")
    assert func_section.name == "get_items"
    assert "async def get_items" in func_section.text
    assert "@router.get" in func_section.text
    assert "@cache" in func_section.text
    assert func_section.start_line == 1


def test_js_async_function() -> None:
    """Test that async function is detected and JSDoc/decorators included."""
    content = """
/**
 * Loads the user.
 */
async function fetchUser(id) {
  return await api.get(id);
}
"""
    sections = parse_sections(content.strip(), Path("test.js"))

    func_section = sections[0]
    assert func_section.name == "fetchUser"
    assert "async function fetchUser" in func_section.text
    assert "/**" in func_section.text
    assert "Loads the user" in func_section.text


def test_js_arrow_function_named() -> None:
    """Test that const x = () => {} yields function section named x."""
    content = """
const x = () => {
  return 0;
};
"""
    sections = parse_sections(content.strip(), Path("test.js"))

    func_section = sections[0]
    assert func_section.kind == "function"
    assert func_section.name == "x"
    assert "=>" in func_section.text