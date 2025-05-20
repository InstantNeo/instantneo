import unittest
from unittest.mock import patch, Mock, MagicMock, call
import json

# Assuming your adapter is in instantneo.adapters.vertex_ai_adapter
from instantneo.adapters.vertex_ai_adapter import VertexAIAdapter

# Import necessary Vertex AI types for mocking
from vertexai.generative_models import (
    Candidate, Content, Part, FinishReason as VertexFinishReason,
    FunctionCall, GenerationResponse, UsageMetadata, PromptFeedback, SafetyRating, HarmCategory
)
# For streaming, the response objects are usually the same (GenerationResponse)
# but yielded as an iterator.


class TestVertexAIAdapter(unittest.TestCase):

    @patch('vertexai.init') # Mock vertexai.init
    def setUp(self, mock_vertex_init):
        self.adapter = VertexAIAdapter(project="test_project", location="us-central1")
        mock_vertex_init.assert_called_once_with(project="test_project", location="us-central1")

    @patch('vertexai.generative_models.GenerativeModel')
    def test_create_chat_completion_text_response(self, MockGenerativeModel):
        # Setup mock response from the Vertex AI / Gemini API
        mock_vertex_response = MagicMock(spec=GenerationResponse)
        
        # Mocking candidate
        mock_candidate = MagicMock(spec=Candidate)
        mock_candidate.finish_reason = VertexFinishReason.STOP
        
        # Mocking content and parts
        mock_part = MagicMock(spec=Part)
        mock_part.text = "Hello from Vertex AI"
        # In Vertex, a Part might not directly have a function_call attribute.
        # Instead, the Part itself can be a function_call.
        # For a text response, we ensure there's no function_call part.
        # Let's assume part.function_call is how the adapter checks, or it iterates parts.
        # The adapter's `create_chat_completion` logic for Vertex checks `part.function_call`.
        
        mock_content = MagicMock(spec=Content)
        mock_content.parts = [mock_part] # A list of Part objects/mocks
        mock_candidate.content = mock_content
        
        mock_candidate.safety_ratings = []
        # mock_candidate.citation_metadata = None # If adapter uses it

        mock_vertex_response.candidates = [mock_candidate]
        
        # Mocking usage metadata
        mock_usage = MagicMock(spec=UsageMetadata)
        mock_usage.prompt_token_count = 12
        mock_usage.candidates_token_count = 22 # This is completion tokens
        # mock_usage.total_token_count = 34 # Sum of prompt and candidates
        mock_vertex_response.usage_metadata = mock_usage

        # Mocking prompt feedback (no blocking)
        mock_prompt_fb = MagicMock(spec=PromptFeedback)
        mock_prompt_fb.block_reason = None
        mock_vertex_response.prompt_feedback = mock_prompt_fb

        # Configure the mock model instance
        mock_model_instance = MockGenerativeModel.return_value
        mock_model_instance.generate_content.return_value = mock_vertex_response

        # Call the adapter method
        messages = [{"role": "user", "content": "Hello Vertex"}]
        response = self.adapter.create_chat_completion(
            model="gemini-1.0-pro", # Example model name
            messages=messages
        )

        # Assertions
        # Check that GenerativeModel was called with expected model_name and other params
        # from _prepare_vertex_request_params
        expected_system_instruction, expected_history = self.adapter.format_messages(messages)
        MockGenerativeModel.assert_called_once_with(
            model_name="gemini-1.0-pro",
            system_instruction=expected_system_instruction, 
            tools=None, # Default
            safety_settings=None # Default
        )
        
        # Check that generate_content was called with contents and other params
        mock_model_instance.generate_content.assert_called_once_with(
            contents=expected_history,
            generation_config=None, # Default
            tool_config=None # Default
        )
        
        self.assertIn("choices", response)
        self.assertEqual(len(response["choices"]), 1)
        self.assertEqual(response["choices"][0]["message"]["content"], "Hello from Vertex AI")
        self.assertEqual(response["choices"][0]["finish_reason"], "stop")
        self.assertNotIn("tool_calls", response["choices"][0]["message"])

        self.assertIn("usage", response)
        self.assertEqual(response["usage"]["prompt_tokens"], 12)
        self.assertEqual(response["usage"]["completion_tokens"], 22)
        self.assertEqual(response["usage"]["total_tokens"], 34)
        
        self.assertEqual(response["model"], "gemini-1.0-pro")

    @patch('vertexai.generative_models.GenerativeModel')
    def test_create_streaming_chat_completion_text_response(self, MockGenerativeModel):
        # Setup mock stream chunks (GenerationResponse objects)
        mock_chunk1_response = MagicMock(spec=GenerationResponse)
        mock_part1 = MagicMock(spec=Part, text="Hello ")
        mock_candidate1 = MagicMock(spec=Candidate, content=MagicMock(spec=Content, parts=[mock_part1]), finish_reason=VertexFinishReason.UNSPECIFIED, safety_ratings=[])
        mock_chunk1_response.candidates = [mock_candidate1]
        mock_chunk1_response.prompt_feedback = MagicMock(spec=PromptFeedback, block_reason=None)
        mock_chunk1_response.usage_metadata = None # Typically not in each chunk

        mock_chunk2_response = MagicMock(spec=GenerationResponse)
        mock_part2 = MagicMock(spec=Part, text="Vertex!")
        mock_candidate2 = MagicMock(spec=Candidate, content=MagicMock(spec=Content, parts=[mock_part2]), finish_reason=VertexFinishReason.STOP, safety_ratings=[])
        mock_chunk2_response.candidates = [mock_candidate2]
        mock_chunk2_response.prompt_feedback = MagicMock(spec=PromptFeedback, block_reason=None)
        # Last chunk might have usage, but adapter doesn't process it from stream currently
        mock_chunk2_response.usage_metadata = MagicMock(spec=UsageMetadata, prompt_token_count=10, candidates_token_count=5)


        # Configure the mock model instance to return an iterable of these chunks
        mock_model_instance = MockGenerativeModel.return_value
        mock_model_instance.generate_content.return_value = [mock_chunk1_response, mock_chunk2_response]

        # Call the adapter method
        messages = [{"role": "user", "content": "Hello Vertex Stream"}]
        stream_responses = list(self.adapter.create_streaming_chat_completion(
            model="gemini-1.0-pro",
            messages=messages
        ))
        
        expected_system_instruction, expected_history = self.adapter.format_messages(messages)

        # Assertions
        MockGenerativeModel.assert_called_once_with(
            model_name="gemini-1.0-pro", system_instruction=expected_system_instruction, tools=None, safety_settings=None
        )
        mock_model_instance.generate_content.assert_called_once_with(
            contents=expected_history,
            generation_config=None, tool_config=None, # Defaults
            stream=True
        )

        self.assertEqual(len(stream_responses), 2)

        # Check first chunk
        chunk1_resp_dict = stream_responses[0]
        self.assertEqual(chunk1_resp_dict["choices"][0]["delta"]["content"], "Hello ")
        self.assertIsNone(chunk1_resp_dict["choices"][0]["finish_reason"]) # Not finished
        self.assertEqual(chunk1_resp_dict["model"], "gemini-1.0-pro")

        # Check second chunk
        chunk2_resp_dict = stream_responses[1]
        self.assertEqual(chunk2_resp_dict["choices"][0]["delta"]["content"], "Vertex!")
        self.assertEqual(chunk2_resp_dict["choices"][0]["finish_reason"], "stop")

    @patch('vertexai.generative_models.GenerativeModel')
    def test_create_chat_completion_with_tool_call(self, MockGenerativeModel):
        mock_response = MagicMock(spec=GenerationResponse)
        mock_candidate = MagicMock(spec=Candidate)
        
        # Mock function call part
        # In Vertex, Part can directly be a function call or contain one.
        # The adapter's logic is: `if part.function_call:`
        mock_fc_obj = MagicMock(spec=FunctionCall) # This is vertexai.generative_models.FunctionCall
        mock_fc_obj.name = "get_weather_vertex"
        mock_fc_obj.args = {"location": "Boston"}
        
        mock_part_fc = MagicMock(spec=Part)
        # Simulate how the SDK might structure this: a Part whose _raw_part has a function_call
        # Or, more directly, the Part object itself has a function_call attribute after SDK processing.
        # We'll mock `part.function_call` as that's what the adapter code checks.
        mock_part_fc.function_call = mock_fc_obj
        mock_part_fc.text = None # No text part if only function call

        mock_candidate.content = MagicMock(spec=Content, parts=[mock_part_fc])
        # When a tool call is made, finish_reason might be STOP or another value.
        # The adapter determines "tool_calls" finish_reason if a function_call is present.
        mock_candidate.finish_reason = VertexFinishReason.STOP 
        mock_candidate.safety_ratings = []

        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata = MagicMock(spec=UsageMetadata, prompt_token_count=20, candidates_token_count=15)
        mock_response.prompt_feedback = MagicMock(spec=PromptFeedback, block_reason=None)

        mock_model_instance = MockGenerativeModel.return_value
        mock_model_instance.generate_content.return_value = mock_response

        tools = [{
            "type": "function",
            "function": {
                "name": "get_weather_vertex",
                "description": "Get current weather for a location",
                "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}
            }
        }]
        messages = [{"role": "user", "content": "What's the weather in Boston via Vertex?"}]
        
        response = self.adapter.create_chat_completion(
            model="gemini-1.0-pro",
            messages=messages,
            tools=tools
        )

        # Assertions
        formatted_tools_vertex = self.adapter.format_tools(tools) 
        expected_system_instruction, expected_history = self.adapter.format_messages(messages)

        MockGenerativeModel.assert_called_once_with(
            model_name="gemini-1.0-pro",
            system_instruction=expected_system_instruction,
            tools=formatted_tools_vertex, # Check that formatted tools are passed
            safety_settings=None 
        )
        mock_model_instance.generate_content.assert_called_once_with(
            contents=expected_history,
            generation_config=None,
            tool_config=None # Default, or could be set if tool_choice was used
        )
        
        self.assertEqual(response["choices"][0]["finish_reason"], "tool_calls")
        self.assertIsNotNone(response["choices"][0]["message"]["tool_calls"])
        tool_call_resp = response["choices"][0]["message"]["tool_calls"][0]
        self.assertEqual(tool_call_resp["function"]["name"], "get_weather_vertex")
        self.assertEqual(json.loads(tool_call_resp["function"]["arguments"]), {"location": "Boston"})
        self.assertIsNone(response["choices"][0]["message"]["content"]) # Content is None when tool_call is present

    @patch('vertexai.generative_models.GenerativeModel')
    def test_content_blocked_safety_vertex(self, MockGenerativeModel):
        mock_response = MagicMock(spec=GenerationResponse)
        mock_candidate = MagicMock(spec=Candidate)
        
        mock_candidate.finish_reason = VertexFinishReason.SAFETY
        mock_candidate.content = MagicMock(spec=Content, parts=[]) 
        
        safety_rating_harmful = MagicMock(spec=SafetyRating)
        safety_rating_harmful.category = HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT
        safety_rating_harmful.probability = SafetyRating.HarmProbability.HIGH # Using actual enum member
        # safety_rating_harmful.blocked = True # Vertex SDK might have this on rating
        mock_candidate.safety_ratings = [safety_rating_harmful]
        
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata = MagicMock(spec=UsageMetadata, prompt_token_count=7, candidates_token_count=0)
        
        # Case 1: Blocking via prompt_feedback
        mock_prompt_fb = MagicMock(spec=PromptFeedback)
        mock_prompt_fb.block_reason = PromptFeedback.BlockReason.SAFETY # Using actual enum member
        mock_prompt_fb.block_reason_message = "Prompt blocked for safety."
        mock_response.prompt_feedback = mock_prompt_fb

        mock_model_instance = MockGenerativeModel.return_value
        mock_model_instance.generate_content.return_value = mock_response
        
        with self.assertRaisesRegex(RuntimeError, "Content generation blocked by Vertex AI due to prompt. Reason: SAFETY. Message: Prompt blocked for safety."):
            self.adapter.create_chat_completion(
                model="gemini-1.0-pro",
                messages=[{"role": "user", "content": "Very risky prompt for Vertex"}]
            )

        # Case 2: Blocking via candidate's finish_reason = SAFETY (prompt_feedback is None)
        mock_response.prompt_feedback.block_reason = None 
        mock_response.prompt_feedback.block_reason_message = ""
        
        response = self.adapter.create_chat_completion(
            model="gemini-1.0-pro",
            messages=[{"role": "user", "content": "Another prompt for Vertex"}]
        )
        self.assertEqual(response["choices"][0]["finish_reason"], "safety")
        self.assertIn("safety_ratings", response["choices"][0])
        # The adapter converts category and probability enums to string names
        self.assertEqual(response["choices"][0]["safety_ratings"][0]["category"], "HARM_CATEGORY_DANGEROUS_CONTENT")
        self.assertEqual(response["choices"][0]["safety_ratings"][0]["probability"], "HIGH")


if __name__ == '__main__':
    unittest.main()
```
