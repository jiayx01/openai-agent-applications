# GPT-35 Turbo 聊天机器人

这个项目是一个使用 OpenAI 的 GPT-35 Turbo 模型构建的聊天机器人，具有网页抓取和天气查询的附加功能。聊天机器人使用 SQLite 来存储聊天记录，并使用 Azure OpenAI 进行与 GPT-35 Turbo 模型的交互。

## 功能

- **聊天记录**：使用 SQLite 存储和检索聊天记录。
- **网页抓取**：从网页中提取内容。
- **天气查询**：根据城市名称获取当前天气信息。

## 安装

### 前提条件

- Python 3.8+
- SQLite
- OpenAI Azure 订阅
- 必要的 Python 包（参见 `requirements.txt`）

### 安装步骤

1. **克隆仓库**：

    ```bash
    git clone https://github.com/yourusername/gpt-35-turbo-instruct-chatbot.git
    cd gpt-35-turbo-instruct-chatbot
    ```

2. **安装依赖**：

    ```bash
    pip install -r requirements.txt
    ```

3. **设置 Azure OpenAI 凭证**：

    更新脚本中的 `client` 实例化部分，使用你的 Azure endpoint 和 API key：

    ```python
    client = AzureOpenAI(
        azure_endpoint="https://your-azure-endpoint.openai.azure.com",
        api_key="your-api-key",
        api_version="2024-02-01"
    )
    ```

4. **创建 SQLite 数据库**：

    运行脚本以初始化数据库：

    ```bash
    python script.py "initialize database"
    ```

## 使用方法

### 运行聊天机器人

要开始聊天，运行脚本并提供提示：

```bash
python script.py "你好，北京的天气怎么样？"
