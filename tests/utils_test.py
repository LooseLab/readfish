import pytest
from readfish.plugins.utils import (
    target_coverage,
    _summary_percent_reference_covered,
    sum_target_coverage,
)
import numpy as np


# Create a mock Aligner instance
class MockAligner:
    @property
    def seq_names(self):
        # Mock the seq_names method to return a list of chromosomes for testing
        return ["chromosome1", "chromosome2"]

    def seq(self, k):
        # Mock the seq method to return a sequence for testing
        if k == "chromosome1":
            return "ATGCATGCATGC"  # Length of 12 characters
        elif k == "chromosome2":
            return "CGTACGTACGTA"  # Length of 12 characters
        return None


@pytest.fixture
def mock_aligner():
    return MockAligner()


def test_target_coverage_numeric(mock_aligner):
    # Test target_coverage with numeric value (non-inf)
    result = target_coverage([(1, 5), (4, 10)], "chromosome1", mock_aligner)
    assert (
        result == 10
    )  # Absolute distance between 1 and 5 is 4, 4 and 10 is 6 so total is 10


def test_target_coverage_inf(mock_aligner):
    # Test target_coverage with np.inf value
    result = target_coverage([(-np.inf, np.inf)], "chromosome1", mock_aligner)
    assert result == 12  # Length of chromosome1 is 12 characters


def test_target_coverage_invalid(mock_aligner):
    # Test target_coverage with invalid chromosome name
    result = target_coverage([(1, 5)], "unknown_chromosome", mock_aligner)
    assert (
        result == 4
    )  # Chromosome not found, but the target is not inf, should return 4. This shouldn't happen as the chromosome
    # should be checked when initialising conf before calling this function.


def test_sum_target_coverage_numeric(mock_aligner):
    # Test sum_target_coverage with numeric values (non-inf)
    data = {"chromosome1": [(1, 5), (7, 10)], "chromosome2": [(2, 6)]}
    result = sum_target_coverage(data, mock_aligner)
    assert result == 11  # Sum of distances (4 + 4) for chromosome1 and chromosome2


def test_sum_target_coverage_inf(mock_aligner):
    # Test sum_target_coverage with np.inf values
    data = {"chromosome1": [(-np.inf, np.inf)], "chromosome2": [(-np.inf, np.inf)]}
    result = sum_target_coverage(data, mock_aligner)
    assert (
        result == 24
    )  # Sum of chromosome lengths (12 + 12) for chromosome1 and chromosome2


def test_sum_target_coverage_invalid_partial_contig(mock_aligner):
    # Test sum_target_coverage with an invalid chromosome name
    data = {"unknown_chromosome": [(1, 5)]}
    result = sum_target_coverage(data, mock_aligner)
    assert (
        result == 4
    )  # Chromosome not found, but the target is not inf, should return 4. This shouldn't happen as the chromosome
    # should be checked when initialising conf before calling this function.


def test_sum_target_coverage_invalid_whole_contig(mock_aligner):
    # Test sum_target_coverage with an invalid chromosome name
    data = {"unknown_chromosome": [(0, float("inf"))]}
    result = sum_target_coverage(data, mock_aligner)
    assert result == 0  # Chromosome not found, and the target is inf, should return 0


def test_sum_target_coverage_empty():
    # Test sum_target_coverage with an empty dictionary
    data = {}
    result = sum_target_coverage(data, MockAligner())
    assert result == 0  # Empty dictionary, should return 0


# Test _summary_percent_reference_covered function
def test_summary_percent_reference_covered(mock_aligner):
    ref_len = sum(len(mock_aligner.seq(sn)) for sn in mock_aligner.seq_names)
    target_intervals = {
        "chromosome1": [(1.0, 5.0)],
        "chromosome2": [(0, np.inf)],
    }
    result = _summary_percent_reference_covered(ref_len, target_intervals, mock_aligner)
    assert result == pytest.approx(66.67)  # Expected result based on provided data

    target_intervals = {"chromosome1": [(1.0, 2.0), (2.0, 4.0)]}
    result = _summary_percent_reference_covered(ref_len, target_intervals, mock_aligner)
    assert result == pytest.approx(
        round((3 / 24) * 100, 2)
    )  # Expected result based on provided data, i.e covering 1 base in a 24 base reference

    # Test with empty target_intervals
    empty_intervals = {}
    result = _summary_percent_reference_covered(ref_len, empty_intervals, mock_aligner)
    assert result == pytest.approx(0.0)  # No coverage when target_intervals are empty
