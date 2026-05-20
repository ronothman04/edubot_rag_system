from rag import ask
from memory import add, get

while True:
    query = input("You: ")

    if query.lower() in ["exit", "quit"]:
        break

    history = get()

    answer = ask(query, history)

    print("AI:", answer)

    add(query, answer)