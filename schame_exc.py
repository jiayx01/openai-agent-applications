import sys
import json
import sqlite3
from typing import List, Dict

from openai.lib.azure import AzureOpenAI

import trafilatura
import requests

# 链接 sqlite 数据库，sqlite 数据库就是一个文本文件，在 connect 方法里写上这个文本文件的路径即可
conn = sqlite3.connect("gpt_35_schame.db")
cursor = conn.cursor()

# 全局使用的 openai client，之后会使用这个 client 进行对话
client = AzureOpenAI(
    azure_endpoint="https://onewo-sweden-central.openai.azure.com",
    api_key="1ecfcb8dd77c47368bd8f971ab166481",
    api_version="2024-02-01"
)

web_crawl_tool = {
    "type": "function",
    "function": {
        "name": "web_crawl_tool",
        "description": """
            这是一个网页抓取工具，你可以传入一个 URL 来获取网页的具体内容；当用户让你总结网页内容时，请使用这个工具获取用户提供的 URL，再根据 URL 的具体内容帮助用户总结网页。
        """,
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "网页的 URL，请从用户的 prompt 中提取出 URL",
                },
            },
        },
        "required": ["url"],
    },
}


def web_crawl(url: str) -> str:
    downloaded = trafilatura.fetch_url(url)
    return trafilatura.extract(downloaded)


# 要让 GPT 帮我们查天气，有哪些步骤
#
# 1. 从用户的参数中提取城市；
# 2. 根据城市名称查询对应的 adcode；
# 3. 拿这个 adcode 调用高德的接口查询天气；
# 4. 把天气信息返回给 gpt，让 gpt 输出内容给用户；

weather_tools = [
    {
        "type": "function",
        "function": {
            "name": "get_city_code",
            "description": """
                根据城市名称查询城市的 adcode，这个 adcode 可以作为调用 get_weather 函数的参数。
            """,
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，请从用户的 prompt 中提取出城市名称",
                    },
                },
            },
            "required": ["city"],
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": """
                根据 adcode 查询当前的天气，adcode 可以通过 get_city_code 获取
            """,
            "parameters": {
                "type": "object",
                "properties": {
                    "adcode": {
                        "type": "string",
                        "description": "城市的 adcode，请通过 get_city_code 获取",
                    },
                },
            },
            "required": ["adcode"],
        }
    },
]


def get_city_code(arguments: Dict[str, any]) -> str:
    # 假装这里就是读取 excel 的逻辑，并且生成了一个 code_map
    code_map = {
        "深圳市": "440300",
        "广州市": "440100",
        "北京市": "110000",
    }
    for city, code in code_map.items():
        if arguments["city"] in city:
            return code
    return None


def get_weather(arguments: Dict[str, any]) -> str:
    response = requests.get("https://restapi.amap.com/v3/weather/weatherInfo",
                            params={"key": "dfd742fab8c930223244b5a9a916768e",
                                    "city": arguments["adcode"]})
    return response.text


tool_map = {
    "get_city_code": get_city_code,
    "get_weather": get_weather,
}


# chat 函数会先从数据库里取出历史聊天记录，然后带上最新的聊天记录去和大模型勾兑
def chat(prompt: str) -> str:
    create_table()
    chat_id = get_chat_id()
    messages = get_messages(chat_id)
    new_user_message = {"content": prompt, "role": "user"}
    messages.append(new_user_message)
    insert_message(chat_id, new_user_message, commit=False)

    while True:
        completions = client.chat.completions.create(
            model="gpt-35-turbo-instruct",
            messages=messages,
            tools=weather_tools,
        )

        choice = completions.choices[0]
        if choice.finish_reason == "tool_calls":
            messages.append(choice.message)
            message_id = insert_message(chat_id, choice.message.model_dump(), commit=False)
            # print(choice.message.model_dump_json())
            insert_tool_calls(message_id, choice.message.model_dump().get("tool_calls"), commit=False)
            for tc in choice.message.tool_calls:
                print(tc.model_dump_json(indent=4))
                tool = tool_map.get(tc.function.name)
                if tool:
                    arguments = json.loads(tc.function.arguments)
                    content = tool(arguments)
                    message = {
                        "role": "tool",
                        "content": json.dumps({"content": content}, ensure_ascii=False),
                        "tool_call_id": tc.id,
                    }
                    insert_message(chat_id, message, commit=False)
                    messages.append(message)
        elif choice.finish_reason == "stop":
            insert_message(chat_id, choice.message.model_dump(), commit=False)
            break

    conn.commit()
    return choice.message.content


def create_table():
    # 建表
    cursor.execute("""
    create table if not exists chat
    (
        id   integer primary key autoincrement,
        name text
    );
    """)

    cursor.execute("""
    create table if not exists message
    (
        id              integer primary key autoincrement,
        content         text,
        role            text not null,
        tool_call_id    text,
        chat_id         integer not null
    );
    """)

    cursor.execute("""
    create table if not exists tool_call
    (
        id                 integer primary key autoincrement,
        tool_id            text not null,
        type               text not null,
        function_name      text,
        function_arguments text,
        message_id         integer not null
    )
    """)

    conn.commit()


def get_chat_id() -> int:
    # 查询数据库里名称是这个的会话
    cursor.execute("""
        SELECT id AS chat_id, name AS chat_name FROM chat WHERE name = 'gpt-35-turbo-instruct' ORDER BY id DESC LIMIT 1
    """)
    row = cursor.fetchone()
    # 如果有记录，那就使用该条记录对应的 chat_id
    if row:
        chat_id, chat_name = row  # (chat_id, chat_name)
        # 假如这个 chat 的消息数量小于 10 条，则使用这个 chat，
        # 如果大于 10 条，则新开启一个 chat
        cursor.execute("""
            SELECT COUNT(*) FROM message WHERE chat_id = ?
        """, [chat_id])
        cnt, = cursor.fetchone()
        if cnt < 100:
            return chat_id
    # 如果没有记录，则新增一条 chat 记录，并使用这个 chat 的 id
    cursor.execute("""
        INSERT INTO chat (name) VALUES ('gpt-35-turbo-instruct');
    """)
    conn.commit()
    cursor.execute("""
        SELECT id AS chat_id FROM chat WHERE name = 'gpt-35-turbo-instruct';
    """)
    chat_id, = cursor.fetchone()
    return chat_id


def insert_message(chat_id: int, message: Dict[str, str], commit=True) -> int:
    cursor.execute("""
        INSERT INTO message (content, role, tool_call_id, chat_id) VALUES(?, ?, ?, ?)
    """, [message["content"], message["role"], message.get("tool_call_id"), chat_id])
    if commit:
        conn.commit()
    return cursor.lastrowid


def insert_tool_calls(message_id: int, tool_calls: List[Dict[str, any]], commit=True):
    for tc in tool_calls:
        cursor.execute("""
            INSERT INTO tool_call (tool_id, type, function_name, function_arguments, message_id)
            VALUES (?, ?, ?, ?, ?);
        """, [tc["id"], tc["type"], tc["function"]["name"], tc["function"]["arguments"], message_id])
    if commit:
        conn.commit()


def get_messages(chat_id: int) -> List[Dict[str, str]]:
    # 从数据库里查出历史的消息
    cursor.execute("""
        SELECT id, content, role, tool_call_id FROM message WHERE chat_id = ? ORDER BY id ASC;
    """, [chat_id])
    rows = cursor.fetchall()
    messages = []
    for (message_id, content, role, tool_call_id) in rows:
        message = {"content": content, "role": role, "tool_call_id": tool_call_id, "tool_calls": []}
        # 查出当前这条消息所包含的 tool_calls
        cursor.execute("""
            SELECT tool_id, type, function_name, function_arguments FROM tool_call WHERE message_id = ?
        """, [message_id])
        tool_call_rows = cursor.fetchall()
        for (tool_id, tool_type, function_name, function_arguments) in tool_call_rows:
            message["tool_calls"].append({
                "id": tool_id,
                "type": tool_type,
                "function": {
                    "name": function_name,
                    "arguments": function_arguments,
                },
            })
        # 如果没有 tool_calls，则删除 tool_calls 这个键值，以避免 openai 接口报错
        if len(message["tool_calls"]) == 0:
            del message["tool_calls"]
        # 如果没有 tool_call_id，则删除 tool_call_id 这个键值，以避免 openai 接口报错
        if message["tool_call_id"] is None:
            del message["tool_call_id"]
        messages.append(message)
    return messages


def main():
    reply = chat(sys.argv[1])
    print("assistant:", reply)


if __name__ == '__main__':
    main()
