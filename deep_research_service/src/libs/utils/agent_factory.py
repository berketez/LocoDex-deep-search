from typing import Any

import yaml

from together_open_deep_research import DeepResearcher


def load_config(config_path: str):
    with open(config_path, "r") as file:
        return yaml.safe_load(file)


def create_agent(config: str, return_instance: bool = False) -> Any:
    """
    Factory method to create an agent with specified configuration.
    """

    config_dict = load_config(config)

    agent_config = config_dict.get("agent")
    agent_type = agent_config.pop("type")

    if agent_type == "deep_researcher":
        agent_config["budget"] = agent_config.pop("max_steps")
        researcher = DeepResearcher(**agent_config)

        if return_instance:
            return researcher

        def research_wrapper(goal: str):
            import asyncio

            return asyncio.run(researcher.research_topic(goal))

        return research_wrapper

    elif agent_type == "langchain_deep_researcher":
        try:
            import uuid

            from langgraph.checkpoint.memory import MemorySaver
            from open_deep_research.graph import builder
        except ImportError as e:
            raise ImportError(
                f"Failed to import required modules for langchain deep researcher: {e}. Make sure langgraph and open_deep_research are installed. Also make sure that the benchmark directory is in your path. Also, you might need to install the with-open-deep-research extra dependencies (see README.md)."
            )

        memory = MemorySaver()
        graph = builder.compile(checkpointer=memory)

        REPORT_STRUCTURE = """Use this structure to create a report on the user-provided topic:

                        1. Introduction (no research needed)
                        - Brief overview of the topic area

                        2. Main Body Sections:
                        - Each section should focus on a sub-topic of the user-provided topic
                        
                        3. Conclusion
                        - Aim for 1 structural element (either a list of table) that distills the main body sections 
                        - Provide a concise summary of the report"""
        
        # Extract configuration parameters
        search_api = agent_config.get("search_api", "tavily")
        planner_provider = agent_config.get("planner_provider")
        planner_model = agent_config.get("planner_model")
        writer_provider = agent_config.get("writer_provider")
        writer_model = agent_config.get("writer_model")
        max_search_depth = agent_config.get("max_search_depth", 3)
        
        def langchain_wrapper(goal: str):
            import asyncio
            
            thread = {
                "configurable": {
                    "thread_id": str(uuid.uuid4()),
                    "search_api": search_api,
                    "planner_provider": planner_provider,
                    "planner_model": planner_model,
                    "writer_provider": writer_provider,
                    "writer_model": writer_model,
                    "max_search_depth": max_search_depth,
                    "report_structure": REPORT_STRUCTURE
                }
            }

            # NOTE: add research prompt to the goal for robust benchmarking purposes
            goal=goal + " You must perform in-depth research to answer the question."
            
            results = []
            
            async def run_graph():
                async for event in graph.astream({"topic": goal}, thread, stream_mode="updates"):
                    results.append(event)
                
                from langgraph.types import Command
                async for event in graph.astream(Command(resume=True), thread, stream_mode="updates"):
                    results.append(event)

                final_state = graph.get_state(thread)
                report = final_state.values.get('final_report')
                
                return report
            
            return asyncio.run(run_graph())
        
        return langchain_wrapper

    elif agent_type == "base_llm":
        model = agent_config.get("model")

        def base_llm_wrapper(goal: str):
            import asyncio

            from libs.utils.llms import asingle_shot_llm_call

            system_prompt = (
                "You are a helpful AI assistant. Answer the user's question accurately and concisely. "
                "Reason through the problem step by step."
            )

            async def get_answer():
                return await asingle_shot_llm_call(model=model, system_prompt=system_prompt, message=goal)

            return asyncio.run(get_answer())

        return base_llm_wrapper

    elif agent_type == "smolagents":
        try:
            from baselines.smolagents_baseline import SmolAgentsTavilySearchTool
            from smolagents import CodeAgent, LiteLLMModel
            from smolagents.default_tools import VisitWebpageTool
        except ImportError as e:
            raise ImportError(
                f"Failed to import required modules for smolagents: {e}. Make sure the benchmark directory is in your path."
            )

        model_id = agent_config.get(
            "model", "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo")

        import os

        api_key = os.environ.get("TOGETHER_API_KEY")
        if not api_key:
            raise ValueError(
                "API key not provided and TOGETHER_API_KEY not found in environment")

        model = LiteLLMModel(model_id=model_id, api_key=api_key)

        tools = []

        if "tools" in agent_config:
            tool_configs = agent_config.pop("tools")
            for item in tool_configs:
                if isinstance(item, str) and item == "TavilySearch":
                    tools.append(SmolAgentsTavilySearchTool())
                elif isinstance(item, dict):
                    tool_name = list(item.keys())[0]
                    if tool_name == "TavilySearch":
                        params = item.get(tool_name, {}).get("params", {})
                        tools.append(SmolAgentsTavilySearchTool(**params))

        tools.append(VisitWebpageTool())
        agent = CodeAgent(
                    tools=tools,
                    model=model,
                    additional_authorized_imports=["numpy", "sympy"],
                    max_steps=10,
                )
        def smolagents_wrapper(goal: str):
            return agent.run(goal)

        return smolagents_wrapper

    else:
        raise ValueError(f"Unknown agent type: {agent_type}")
