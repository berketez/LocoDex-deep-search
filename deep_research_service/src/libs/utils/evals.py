from dataclasses import dataclass
from typing import Callable

import tenacity
from litellm import completion


@dataclass
class Result:
    question: str
    agent_answer: str
    correct_answer: str


ScoringFunction = Callable[[Result], bool]


@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_exponential(multiplier=1, min=4, max=15))
def llm_as_a_judge_scoring(result: Result) -> bool:
    prompt = f"""
    Given the following question and answer, evaluate the answer against the correct answer:

    <question>
    {result.question}
    </question>

    <agent_answer>
    {result.agent_answer}
    </agent_answer>

    <correct_answer>
    {result.correct_answer}
    </correct_answer>

    Note that the agent answer might be a long text containing a lot of information or it might be a short answer.
    
    You should read the entire text and think if the agent answers the question somewhere
    in the text. You should try to be flexible with the answer but careful. 
    
    For example, answering with names instead of name and surname is fine.

    The important thing is that the answer of the agent either contains the correct answer or is equal to the correct answer.
    
    <reasoning>
    The agent answer is correct because I can read that ....
    </reasoning>

    <answer>
    1
    </answer>

    Otherwise, return

    <reasoning>
    The agent answer is incorrect because there is ...
    </reasoning>

    <answer>
    0
    </answer>

    """

    messages = [
        {"role": "system", "content": "You are an helpful assistant that returns a number between 0 and 1."},
        {"role": "user", "content": prompt},
    ]
    answer = (
        completion(
            model="together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",
            messages=messages,
            max_tokens=1000,
            temperature=0.0,
        )
        .choices[0]  # type: ignore
        .message["content"]  # type: ignore
    )

    return bool(int(answer.split("<answer>")[1].split("</answer>")[0].strip()))
