"""Text batching nodes migrated from ComfyUI-batching-nodes-SKEBA."""


class PromptLoopNode:
    """Split text into prompts for ComfyUI list-based batch execution."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "prompt 1\nprompt 2\nprompt 3",
                    },
                ),
                "delimiter": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "\n",
                    },
                ),
                "skip_empty": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("STRING", "INT", "INT", "SKEBA_PROMPT_LIST")
    RETURN_NAMES = ("prompts_list", "count", "prompt_numbers", "prompt_batch")
    OUTPUT_IS_LIST = (True, False, True, False)
    FUNCTION = "split_prompts"
    CATEGORY = "Skeba AI Nodes - Utilities"

    def split_prompts(self, text, delimiter="\n", skip_empty=True):
        prompts = text.split(delimiter)

        if skip_empty:
            prompts = [prompt.strip() for prompt in prompts if prompt.strip()]
        else:
            prompts = [prompt.strip() for prompt in prompts]

        count = len(prompts)
        prompt_numbers = list(range(1, count + 1))
        return (prompts, count, prompt_numbers, prompts)


class PromptFromListNode:
    """Select one prompt from the atomic prompt-batch output."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt_batch": ("SKEBA_PROMPT_LIST", {"forceInput": True}),
                "index": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 10000,
                        "forceInput": True,
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("prompt", "current_prompt")
    FUNCTION = "get_prompt"
    CATEGORY = "Skeba AI Nodes - Utilities"

    def get_prompt(self, prompt_batch, index):
        if isinstance(prompt_batch, list) and prompt_batch:
            actual_index = index % len(prompt_batch)
            return (prompt_batch[actual_index], actual_index + 1)

        return ("", 0)
