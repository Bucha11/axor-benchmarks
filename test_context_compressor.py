import pytest
from axor_core.contracts.context import ContextFragment
from axor_core.contracts.policy import CompressionMode
from context_compressor import ContextCompressor


class TestContextCompressor:
    """Unit tests for ContextCompressor.compress()"""

    @pytest.fixture
    def compressor(self):
        return ContextCompressor()

    def test_compress_empty_fragments(self, compressor):
        """Test compression with no fragments returns empty result"""
        result = compressor.compress([], CompressionMode.BALANCED, current_turn=1)
        
        assert result.fragments == []
        assert result.before_tokens == 0
        assert result.after_tokens == 0
        assert result.compression_ratio == 1.0
        assert result.strategies_applied == []

    def test_compress_pinned_never_touched(self, compressor):
        """Test that PINNED fragments are never modified"""
        fragments = [
            ContextFragment(
                kind="assistant_prose",
                content="a" * 5000,  # Very large content
                token_estimate=5000,
                source="test",
                relevance=1.0,
                value="pinned",
                turn=1,
            )
        ]
        
        result = compressor.compress(fragments, CompressionMode.AGGRESSIVE, current_turn=10)
        
        assert len(result.fragments) == 1
        assert result.fragments[0].content == fragments[0].content
        assert result.fragments[0].token_estimate == 5000
        assert result.before_tokens == 5000
        assert result.after_tokens == 5000

    def test_compress_removes_empty_working_fragments(self, compressor):
        """Test that empty WORKING fragments are removed"""
        fragments = [
            ContextFragment(
                kind="tool_result",
                content="   \n  ",  # Empty
                token_estimate=0,
                source="test",
                relevance=1.0,
                value="working",
                turn=1,
            ),
            ContextFragment(
                kind="tool_result",
                content="actual content",
                token_estimate=10,
                source="test",
                relevance=1.0,
                value="working",
                turn=1,
            )
        ]
        
        result = compressor.compress(fragments, CompressionMode.BALANCED, current_turn=1)
        
        assert len(result.fragments) == 1
        assert result.fragments[0].content == "actual content"
        assert "remove_empty" in result.strategies_applied

    def test_compress_different_modes(self, compressor):
        """Test that different compression modes affect aggressiveness"""
        fragments = [
            ContextFragment(
                kind="assistant_prose",
                content="x" * 1000,
                token_estimate=1000,
                source="test",
                relevance=1.0,
                value="working",
                turn=1,
            )
        ]
        
        # LIGHT mode - should keep more
        result_light = compressor.compress(
            fragments.copy(), CompressionMode.LIGHT, current_turn=1
        )
        
        # AGGRESSIVE mode - should compress more
        result_aggressive = compressor.compress(
            fragments.copy(), CompressionMode.AGGRESSIVE, current_turn=1
        )
        
        # Aggressive should result in smaller or equal token count
        assert result_aggressive.after_tokens <= result_light.after_tokens

    def test_compress_fragment_value_order(self, compressor):
        """Test that fragments are ordered: pinned, knowledge, working, ephemeral"""
        fragments = [
            ContextFragment(
                kind="tool_result", content="ephemeral", token_estimate=10,
                source="test", relevance=1.0, value="ephemeral", turn=1
            ),
            ContextFragment(
                kind="tool_result", content="working", token_estimate=10,
                source="test", relevance=1.0, value="working", turn=1
            ),
            ContextFragment(
                kind="tool_result", content="pinned", token_estimate=10,
                source="test", relevance=1.0, value="pinned", turn=1
            ),
            ContextFragment(
                kind="tool_result", content="knowledge", token_estimate=10,
                source="test", relevance=1.0, value="knowledge", turn=1
            ),
        ]
        
        result = compressor.compress(fragments, CompressionMode.BALANCED, current_turn=1)
        
        assert result.fragments[0].content == "pinned"
        assert result.fragments[1].content == "knowledge"
        assert result.fragments[2].content == "working"
        assert result.fragments[3].content == "ephemeral"

    def test_compress_calculates_ratio(self, compressor):
        """Test that compression ratio is correctly calculated"""
        fragments = [
            ContextFragment(
                kind="tool_result",
                content="test content",
                token_estimate=100,
                source="test",
                relevance=1.0,
                value="working",
                turn=1,
            )
        ]
        
        result = compressor.compress(fragments, CompressionMode.BALANCED, current_turn=1)
        
        expected_ratio = result.after_tokens / result.before_tokens
        assert result.compression_ratio == expected_ratio
        assert result.before_tokens == 100
