from google.adk.tools import ToolContext

QUESTIONS = [
    "What is your favorite color?",
    "What is your favorite animal?",
    "What is your favorite food?",
    "What is your favorite movie?",
    "What is your favorite book?",
    "What is your favorite song?",
    "What is your favorite place to travel?",
    "What is your favorite hobby?",
    "What is your dream job?",
    "What is one thing you want to learn?",
]

"""
The "Brainstorming" Agent
=========================

SESSION 1 (Setting the Preference)
----------------------------------
User: "I want to answer 3 questions."
  -> Agent stores "user:num_iterations = 3"  <-- PERSISTS FOREVER
  -> Agent stores "current_iteration = 1"    <-- VANISHES AT END OF SESSION

      [ ... User closes browser ... ]

SESSION 2 (The "Magic" Memory)
----------------------------------
User: "Let's start."
  -> Agent loads "user:num_iterations" (It remembers 3!)
  -> Agent initializes "current_iteration = 0" (New session, fresh counter)
  -> Agent: "Okay, Question 1 of 3..."
"""


def set_iterations(num_iterations: int, tool_context: ToolContext):
    """
    Sets the number of iterations for the task.
    """
    if num_iterations > len(QUESTIONS):
        return f"You can only ask up to {len(QUESTIONS)} questions."
    else:
        tool_context.state["user:num_iterations"] = num_iterations
        tool_context.state["user:num_iterations_instructions"] = """
            But we do know,
            so you should start asking questions by calling the `run_task` tool.
        """
        return f"I'll remember that you want me to ask you {num_iterations} questions."

def run_task(tool_context: ToolContext):
    """
    Runs the task multiple times.
    """
    num_iterations = tool_context.state.get("user:num_iterations", 1)
    current_iteration = tool_context.state.get("current_iteration", 0)

    if current_iteration < num_iterations and current_iteration < len(QUESTIONS):
        question = QUESTIONS[current_iteration]
        current_iteration += 1
        tool_context.state["current_iteration"] = current_iteration
        return {
            "question": question,
            "question_number": current_iteration,
            "num_questions": num_iterations,
            "complete": False,
        }
    else:
        return {"complete": True}
