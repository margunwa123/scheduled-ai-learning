"""
The task: a two-call journal assistant. Take a single short journal entry (hardcode one, or read it from input()) and send it through two separate Gemini calls that need opposite configurations

Deliverable: one script, both calls run back-to-back on the same input, Call A’s output visibly streaming to the terminal, Call B’s output as a clean parsed JSON object (or a warning if truncated/malformed).
"""

# section_1.py
from dotenv import load_dotenv
from google import genai
import json


def read_content() -> str:
    with open("gemini/section_1_input.txt", "r", encoding="utf-8") as file:
        return file.read()


def is_max_token_limit(finish_reason: str) -> bool:
    if str(finish_reason) == "MAX_TOKENS" or finish_reason == 2:
        return True

    return False


"""

Call A — reflection coach (freeform). system_instruction establishes the model as a warm journaling coach that responds with 2–3 sentences of reflection plus one open-ended question — tone should feel human and varied, not clinical. Pick a temperature that fits that (and leave a one-line comment on why). Set max_tokens sized for a short reply. Turn streaming on, and print each chunk as it arrives rather than waiting for the full response — this is the case where streaming actually earns its keep.
"""


def call_a(journal_content: str, client):
    stream = client.interactions.create(
        model="gemini-3.8-flash",
        system_instruction="You are a warm journaling coach that responds query with a maximum of 2-3 sentences of reflection. You will end your response, with 1 question. The tone should feel human and varied, for example instead of telling 'you are a bit wrong on that', you can say 'I'm sorry to hear that, maybe you can try ...'.The input you'll receive is the journal of the person that's writing it.",
        generation_config={
            "max_output_tokens": 1000,
            "thinking_level": "low",  # lowest level this model supports — "minimal" gets a 400 error on 3.8 Flash
        },
        stream=True,
        input=journal_content,
    )

    for event in stream:
        if event.event_type == "step.delta" and event.delta.type == "text":
            print(event.delta.text, end="", flush=True)
        elif event.event_type == "interaction.completed":
            if event.interaction.status == "incomplete":
                print("\nOutput incomplete (likely hit max_output_tokens)")
                break

    print()


"""
Call B — mood tagger (structured). Same journal entry, different system_instruction: a strict classifier that outputs only JSON shaped like {"mood": "happy"|"sad"|"anxious"|"neutral"|"excited"|"angry", "needs_followup": bool}. Pick a temperature appropriate for consistent classification (comment on why it’s different from Call A). Set a tight max_tokens sized to that small JSON payload. Streaming off — and here’s the extra piece: check the response’s finish_reason; if it’s MAX_TOKENS, print a warning instead of silently trying to parse truncated JSON. Then json.loads() the result and print the parsed dict (wrap it so a malformed response doesn’t crash the script).
"""


def call_b(journal_content: str, client):
    interaction = client.interactions.create(
        model="gemini-3.8-flash",
        system_instruction='You are a mood tagger, whose job is to read a journal entry, and classify the mood based on the journal. The output should be a plain JSON object with 2 fields: {{"mood": "happy"|"sad"|"anxious"|"neutral"|"excited"|"angry", "needs_followup": bool }}. You need to classify consistently, so do not give a creative tagging, and stick to the json format. Also, do not add markdown tags to the output like ```json, or anything. Just output the plain json object.',
        generation_config={
            "max_output_tokens": 500,
            "thinking_level": "low",
        },
        stream=False,
        input=journal_content,
    )

    if interaction.status != "completed":
        print(
            f"\n[Warning: interaction did not complete — status={interaction.status}]"
        )
        if interaction.errors:
            for err in interaction.errors:
                print(f"  {err.code}: {err.message}")
        if interaction.usage:
            u = interaction.usage
            print(
                f"  thought_tokens={u.total_thought_tokens}, output_tokens={u.total_output_tokens}, total={u.total_tokens}"
            )
        return

    if not interaction.output_text:
        print("\n[Warning: model returned no text output.]")
        return

    print(f"Raw answer: {interaction.output_text}")
    try:
        parsed_result = json.loads(interaction.output_text)
        print(parsed_result)
    except Exception as e:
        print(f"Error occured while parsing json {e}")

    print()


def main():
    journal_content = read_content()

    if journal_content == "":
        print("Error: no journal text")
        return

    load_dotenv()
    client = genai.Client()  # picks up GEMINI_API_KEY from the environment

    print("#A : Journalling Coach")
    call_a(journal_content, client)

    print("#B : Mood Tagger")
    call_b(journal_content, client)


if __name__ == "__main__":
    main()
