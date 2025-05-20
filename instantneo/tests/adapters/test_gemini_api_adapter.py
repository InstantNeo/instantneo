import unittest
from unittest.mock import patch, Mock, MagicMock, call
import json
from instantneo.adapters.gemini_api_adapter import GeminiAPIAdapter
# Use google.generativeai.types directly for mocking complex types if needed
import google.generativeai.types as genai_types

class TestGeminiAPIAdapter(unittest.TestCase):

    @patch('google.generativeai.configure') # Mock configure if called in init
    def setUp(self, mock_configure):
        self.adapter = GeminiAPIAdapter(api_key="test_key")
        mock_configure.assert_called_once_with(api_key="test_key")

    @patch('google.generativeai.GenerativeModel')
    def test_create_chat_completion_text_response(self, MockGenerativeModel):
        # Setup mock response from the Gemini API
        mock_gemini_response = MagicMock(spec=genai_types.GenerateContentResponse)
        
        # Mocking candidate
        mock_candidate = MagicMock(spec=genai_types.Candidate)
        mock_candidate.finish_reason = genai_types.FinishReason.STOP
        
        # Mocking content and parts
        mock_part = MagicMock(spec=genai_types.Part)
        mock_part.text = "Hello from Gemini"
        mock_part.function_call = None 
        
        mock_candidate.content = MagicMock(spec=genai_types.Content)
        mock_candidate.content.parts = [mock_part]
        
        mock_candidate.safety_ratings = []
        mock_candidate.citation_metadata = None # Assuming no citation for this test

        mock_gemini_response.candidates = [mock_candidate]
        
        # Mocking usage metadata
        mock_usage_metadata = MagicMock(spec=genai_types.UsageMetadata)
        mock_usage_metadata.prompt_token_count = 10
        mock_usage_metadata.candidates_token_count = 20
        # Gemini API GenerateContentResponse might not directly have total_token_count,
        # but UsageMetadata for the candidate might.
        # Let's assume candidates_token_count is what we use for completion_tokens.
        # Total tokens is derived.
        mock_gemini_response.usage_metadata = mock_usage_metadata

        # Mocking prompt feedback (no blocking)
        mock_prompt_feedback = MagicMock(spec=genai_types.PromptFeedback)
        mock_prompt_feedback.block_reason = None
        mock_gemini_response.prompt_feedback = mock_prompt_feedback

        # Configure the mock model instance
        mock_model_instance = MockGenerativeModel.return_value
        mock_model_instance.generate_content.return_value = mock_gemini_response

        # Call the adapter method
        messages = [{"role": "user", "content": "Hello"}]
        response = self.adapter.create_chat_completion(
            model="gemini-pro",
            messages=messages
        )

        # Assertions
        MockGenerativeModel.assert_called_once_with(
            model_name="gemini-pro",
            system_instruction=None, # Default from format_messages
            tools=None, # Default
            safety_settings=None, # Default
            generation_config=None, # Default
            tool_config=None # Default
        )
        mock_model_instance.generate_content.assert_called_once_with(
            contents=[{'role': 'user', 'parts': [{'text': 'Hello'}]}] 
        )
        
        self.assertIn("choices", response)
        self.assertEqual(len(response["choices"]), 1)
        self.assertEqual(response["choices"][0]["message"]["content"], "Hello from Gemini")
        self.assertEqual(response["choices"][0]["finish_reason"], "stop")
        self.assertNotIn("tool_calls", response["choices"][0]["message"])

        self.assertIn("usage", response)
        self.assertEqual(response["usage"]["prompt_tokens"], 10)
        self.assertEqual(response["usage"]["completion_tokens"], 20)
        self.assertEqual(response["usage"]["total_tokens"], 30)
        
        self.assertEqual(response["model"], "gemini-pro")

    @patch('google.generativeai.GenerativeModel')
    def test_create_streaming_chat_completion_text_response(self, MockGenerativeModel):
        # Setup mock stream chunks
        mock_chunk1 = MagicMock(spec=genai_types.GenerateContentResponse)
        mock_part1 = MagicMock(spec=genai_types.Part)
        mock_part1.text = "Hello "
        mock_part1.function_call = None
        mock_candidate1 = MagicMock(spec=genai_types.Candidate)
        mock_candidate1.content = MagicMock(spec=genai_types.Content)
        mock_candidate1.content.parts = [mock_part1]
        mock_candidate1.finish_reason = genai_types.FinishReason.UNSPECIFIED # Not finished yet
        mock_candidate1.safety_ratings = []
        mock_chunk1.candidates = [mock_candidate1]
        mock_chunk1.prompt_feedback = MagicMock(block_reason=None)
        mock_chunk1.usage_metadata = None # Usage typically not in each chunk

        mock_chunk2 = MagicMock(spec=genai_types.GenerateContentResponse)
        mock_part2 = MagicMock(spec=genai_types.Part)
        mock_part2.text = "Gemini!"
        mock_part2.function_call = None
        mock_candidate2 = MagicMock(spec=genai_types.Candidate)
        mock_candidate2.content = MagicMock(spec=genai_types.Content)
        mock_candidate2.content.parts = [mock_part2]
        mock_candidate2.finish_reason = genai_types.FinishReason.STOP # Finished here
        mock_candidate2.safety_ratings = []
        mock_chunk2.candidates = [mock_candidate2]
        mock_chunk2.prompt_feedback = MagicMock(block_reason=None)
        # Last chunk might have usage metadata, but adapter doesn't currently process it from stream
        mock_chunk2.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=5)


        # Configure the mock model instance to return an iterable of these chunks
        mock_model_instance = MockGenerativeModel.return_value
        mock_model_instance.generate_content.return_value = [mock_chunk1, mock_chunk2]

        # Call the adapter method
        messages = [{"role": "user", "content": "Hello Gemini!"}]
        stream_responses = list(self.adapter.create_streaming_chat_completion(
            model="gemini-pro",
            messages=messages
        ))

        # Assertions
        MockGenerativeModel.assert_called_once_with(
            model_name="gemini-pro",
            system_instruction=None, tools=None, safety_settings=None, generation_config=None, tool_config=None
        )
        mock_model_instance.generate_content.assert_called_once_with(
            contents=[{'role': 'user', 'parts': [{'text': 'Hello Gemini!'}]}],
            stream=True
        )

        self.assertEqual(len(stream_responses), 2)

        # Check first chunk
        chunk1_resp = stream_responses[0]
        self.assertEqual(chunk1_resp["choices"][0]["delta"]["content"], "Hello ")
        self.assertIsNone(chunk1_resp["choices"][0]["finish_reason"]) # Not finished in first chunk
        self.assertEqual(chunk1_resp["model"], "gemini-pro")

        # Check second chunk
        chunk2_resp = stream_responses[1]
        self.assertEqual(chunk2_resp["choices"][0]["delta"]["content"], "Gemini!")
        self.assertEqual(chunk2_resp["choices"][0]["finish_reason"], "stop")

    @patch('google.generativeai.GenerativeModel')
    def test_create_chat_completion_with_tool_call(self, MockGenerativeModel):
        mock_response = MagicMock(spec=genai_types.GenerateContentResponse)
        mock_candidate = MagicMock(spec=genai_types.Candidate)
        
        # Mock function call part
        mock_function_call = MagicMock(spec=genai_types.FunctionCall)
        mock_function_call.name = "get_weather"
        mock_function_call.args = {"location": "Paris"}
        
        mock_part_fc = MagicMock(spec=genai_types.Part)
        mock_part_fc.function_call = mock_function_call
        mock_part_fc.text = None # No text part if only function call

        mock_candidate.content = MagicMock(spec=genai_types.Content)
        mock_candidate.content.parts = [mock_part_fc]
        # When a tool call is made, finish_reason is typically FUNCTION or TOOL_USE
        # The adapter maps this to "tool_calls"
        mock_candidate.finish_reason = genai_types.FinishReason.STOP # Let's assume it stops after a tool call for this mock, adapter handles it
        mock_candidate.safety_ratings = []
        mock_candidate.citation_metadata = None

        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata = MagicMock(prompt_token_count=15, candidates_token_count=10)
        mock_response.prompt_feedback = MagicMock(block_reason=None)

        mock_model_instance = MockGenerativeModel.return_value
        mock_model_instance.generate_content.return_value = mock_response

        tools = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather",
                "parameters": {"type": "object", "properties": {"location": {"type": "string"}}}
            }
        }]
        messages = [{"role": "user", "content": "What's the weather in Paris?"}]
        
        response = self.adapter.create_chat_completion(
            model="gemini-pro",
            messages=messages,
            tools=tools
        )

        # Assertions
        formatted_tools = self.adapter.format_tools(tools) # Get what the adapter would format
        MockGenerativeModel.assert_called_once_with(
            model_name="gemini-pro",
            system_instruction=None,
            tools=formatted_tools, # Check that formatted tools are passed
            safety_settings=None,
            generation_config=None,
            tool_config=None
        )
        
        self.assertEqual(response["choices"][0]["finish_reason"], "tool_calls")
        self.assertIsNotNone(response["choices"][0]["message"]["tool_calls"])
        tool_call_resp = response["choices"][0]["message"]["tool_calls"][0]
        self.assertEqual(tool_call_resp["function"]["name"], "get_weather")
        self.assertEqual(json.loads(tool_call_resp["function"]["arguments"]), {"location": "Paris"})
        self.assertIsNone(response["choices"][0]["message"]["content"]) # Content is None when tool_call is present

    @patch('google.generativeai.GenerativeModel')
    def test_content_blocked_safety(self, MockGenerativeModel):
        mock_response = MagicMock(spec=genai_types.GenerateContentResponse)
        mock_candidate = MagicMock(spec=genai_types.Candidate)
        
        mock_candidate.finish_reason = genai_types.FinishReason.SAFETY
        mock_candidate.content = MagicMock(spec=genai_types.Content, parts=[]) # No content parts
        
        # Mock safety ratings
        safety_rating_harmful = MagicMock(spec=genai_types.SafetyRating)
        safety_rating_harmful.category = genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT
        safety_rating_harmful.probability = genai_types.SafetyRating.HarmProbability.HIGH
        # safety_rating_harmful.blocked = True # This might be on the feedback, not rating itself
        mock_candidate.safety_ratings = [safety_rating_harmful]
        
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata = MagicMock(prompt_token_count=5, candidates_token_count=0)
        
        # Mock prompt feedback indicating blocking
        mock_prompt_feedback = MagicMock(spec=genai_types.PromptFeedback)
        mock_prompt_feedback.block_reason = genai_types.PromptFeedback.BlockReason.SAFETY
        mock_prompt_feedback.block_reason_message = "Content blocked due to safety reasons."
        mock_response.prompt_feedback = mock_prompt_feedback # This is for prompt-level blocking

        mock_model_instance = MockGenerativeModel.return_value
        mock_model_instance.generate_content.return_value = mock_response
        
        # Test case 1: Blocking via prompt_feedback
        with self.assertRaisesRegex(RuntimeError, "Content blocked due to: SAFETY. Details: Content blocked due to safety reasons."):
            self.adapter.create_chat_completion(
                model="gemini-pro",
                messages=[{"role": "user", "content": "Risky prompt"}]
            )

        # Test case 2: Blocking via candidate finish_reason = SAFETY (and prompt_feedback is None)
        mock_response.prompt_feedback.block_reason = None # Simulate no prompt-level blocking
        mock_response.prompt_feedback.block_reason_message = ""
        
        # The adapter should still create a response but with finish_reason "safety"
        # and include safety_ratings in the choice.
        response = self.adapter.create_chat_completion(
            model="gemini-pro",
            messages=[{"role": "user", "content": "Another prompt"}]
        )
        self.assertEqual(response["choices"][0]["finish_reason"], "safety")
        self.assertIn("safety_ratings", response["choices"][0])
        self.assertEqual(response["choices"][0]["safety_ratings"]["HARM_CATEGORY_DANGEROUS_CONTENT"], "HIGH")


if __name__ == '__main__':
    unittest.main()
```
