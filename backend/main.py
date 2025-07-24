from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List


app = FastAPI()

class TodoCreate(BaseModel):
    title: str
    completed: bool = False

class Todo(TodoCreate):
    id: int


todos: List[Todo] = []
next_id: int = 1
    
@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/todos")
def get_todos():
    return [todo.dict() for todo in todos]

@app.post("/todos")
def create_todo(todo: TodoCreate):
    global next_id
    new_todo = Todo(id=next_id, title=todo.title, completed=todo.completed)
    todos.append(new_todo)
    next_id += 1
    return new_todo.dict()

@app.put("/todos/{todo_id}")
def update_todo(todo_id: int, update: Todo):
    for todo in todos:
        if todo.id == todo_id:
            todo.title = update.title
            todo.completed = update.completed
            return todo.dict()
    raise HTTPException(status_code=404, detail="Todo not found")

@app.delete("/todos/{todo_id}")
def delete_todo(todo_id: int):
    global todos
    for todo in todos:
        if todo.id == todo_id:
            todos.remove(todo)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Todo not found")
