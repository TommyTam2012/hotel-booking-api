# agent_bcm.py
import os, json, requests
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

BASE_URL = os.getenv("BCM_API_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("OPENAI_API_KEY") or "YOUR_OPENAI_API_KEY"

@tool("GetFAQ", return_direct=False)
def get_faq_tool(intent: str) -> str:
    """Get an FAQ answer by intent. Input: intent string like 'course_duration'."""
    r = requests.get(f"{BASE_URL}/faq/{intent}", timeout=10)
    if r.status_code != 200:
        return f"ERROR {r.status_code}: {r.text}"
    return r.text

@tool("GetRecentEnrollments", return_direct=False)
def get_recent_tool(qs: str = "") -> str:
    """Fetch recent enrollments. Input may be empty, '?limit=5', or '?source=docs'."""
    url = f"{BASE_URL}/enrollments/recent{qs}"
    r = requests.get(url, timeout=10)
    if r.status_code != 200:
        return f"ERROR {r.status_code}: {r.text}"
    return r.text

@tool("CreateEnrollment", return_direct=False)
def post_enroll_tool(payload_json: str) -> str:
    """Create an enrollment. Input: JSON string with keys like full_name, email, program_code, source."""
    try:
        data = json.loads(payload_json)
    except Exception as e:
        return f"Invalid JSON: {e}"
    r = requests.post(f"{BASE_URL}/enroll", json=data, timeout=10)
    if r.status_code != 200:
        return f"ERROR {r.status_code}: {r.text}"
    return r.text

tools = [get_faq_tool, get_recent_tool, post_enroll_tool]

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=API_KEY)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system",
         "You are BCM Crew Ops. Use the tools to query FAQs and enrollments. "
         "If asked to enroll, call CreateEnrollment with a JSON string. Be concise."),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

if __name__ == "__main__":
    print(f"Using BCM API at: {BASE_URL}")

    print("\n=== DEMO 1: FAQ ===")
    out = executor.invoke({"input": "Ask GetFAQ for intent course_duration."})
    print(out["output"])

    print("\n=== DEMO 2: Recent ===")
    out = executor.invoke({"input": "Use GetRecentEnrollments with '?limit=2'."})
    print(out["output"])

    print("\n=== DEMO 3: Enroll ===")
    payload = json.dumps({
        "full_name": "LangChain Agent",
        "email": "agent@example.com",
        "program_code": "GI",
        "source": "agent"
    })
    out = executor.invoke({"input": f'Call CreateEnrollment with this JSON: {payload}'})
    print(out["output"])
