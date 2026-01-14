import asyncio

from app.domain.tools.files.dispatcher import manage_file


async def test_manage_file():
    print("Testing manage_file Dispatcher...")

    test_file = "test_dispatch.txt"
    test_content = "Hello Dispatcher"

    # 1. Create
    print(f"Action: create {test_file}")
    res = await manage_file.ainvoke({
        "action": "create",
        "path": test_file,
        "content": test_content
    })
    print(res)
    assert "Successfully wrote" in res

    # 2. Read
    print(f"Action: read {test_file}")
    res = await manage_file.ainvoke({
        "action": "read",
        "path": test_file
    })
    print(f"Content: {res}")
    assert test_content in res

    # 3. List
    print("Action: list .")
    res = await manage_file.ainvoke({
        "action": "list",
        "path": "."
    })
    print(f"List Result: {res[:50]}...")
    assert test_file in res

    # 4. Clean up (Delete)
    print(f"Action: delete {test_file}")
    res = await manage_file.ainvoke({
        "action": "delete",
        "path": test_file
    })
    print(res)
    assert "Successfully deleted" in res

    print("Dispatcher Test Passed!")

if __name__ == "__main__":
    asyncio.run(test_manage_file())
