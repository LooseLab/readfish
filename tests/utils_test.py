import pytest
from readfish.plugins.utils import (
    _summary_percent_reference_covered,
    get_contig_lengths,
    sum_target_coverage,
    _calculate_length,
    TARGET_INTERVAL,
)
from contextlib import nullcontext


# Create a mock Aligner instance
class MockAligner:
    def __init__(self):
        self._seq_names = ["chromosome1", "chromosome2"]

    @property
    def seq_names(self):
        # Mock the seq_names method to return a list of chromosomes for testing
        return self._seq_names

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


class MockTargets:
    def __init__(self, targets_data):
        self.targets_data = targets_data

    def iter_targets(self):
        for data in self.targets_data:
            chromosome, start, end, strand = data
            yield TARGET_INTERVAL(chromosome, start, end, strand)


@pytest.fixture
def targets_data(request):
    return request.param


@pytest.fixture
def mock_targets(targets_data):
    return MockTargets(targets_data)


targets_test_data = [
    (
        [("chromosome1", 0, 100, "+"), ("chromosome2", 500, 700, "-")],
        300,  # Expected answer for test case 1
    ),
    (
        [("chromosome3", 20, 30, "+"), ("chromosome4", 35, 45, "-")],
        20,  # Expected answer for test case 2
    ),
]

summary_test_data = [
    (
        [("chromosome1", 0, 3, "+"), ("chromosome2", 3, 6, "-")],
        nullcontext(25),  # Expected answer for test case 1
    ),
    (
        [("chromosome1", 0, 12, "+"), ("chromosome2", 0, float("inf"), "-")],
        nullcontext(100),  # Expected answer for test case 2
    ),
    (
        [("chromosome3", 0, float("inf"), "-")],
        pytest.raises(KeyError),  # Expected error for test case 3
    ),
]

# Mock genomes dictionary
genomes = {
    "chromosome1": 1000,
    "chromosome2": 2000,
}


def test_get_contig_lengths(mock_aligner):
    # Create a mock Aligner with known contigs and lengths
    expected_lengths = {"chromosome1": 12, "chromosome2": 12}

    # Call the function and check if it returns the expected lengths
    result = get_contig_lengths(mock_aligner)
    assert result == expected_lengths


def test_get_contig_lengths_duplicate_sequence_name(mock_aligner):
    # Create a mock Aligner with a duplicate sequence name
    mock_aligner._seq_names = ["chromosome1", "chromosome1"]

    # Check if the function raises a RuntimeError for duplicate sequence names
    with pytest.raises(RuntimeError):
        get_contig_lengths(mock_aligner)


# Tests for _calculate_length function
def test_calculate_length_with_interval():
    target_interval = TARGET_INTERVAL("chromosome1", 100, 200, "+")
    result = _calculate_length(target_interval, genomes)
    assert result == 100  # Absolute distance between start and stop


def test_calculate_length_with_inf():
    target_interval = TARGET_INTERVAL("chromosome1", 0, float("inf"), "+")
    result = _calculate_length(target_interval, genomes)
    assert result == 1000  # Length of chromosome1


# Tests for sum_target_coverage function
def test_sum_target_coverage_empty_targets():
    targets = []  # Empty list of targets
    result = sum_target_coverage(targets, genomes)
    assert result == 0  # No targets, so coverage is 0


@pytest.mark.parametrize(
    "targets_data, expected_answer", targets_test_data, indirect=["targets_data"]
)
def test_sum_target_coverage_with_intervals(mock_targets, expected_answer):
    result = sum_target_coverage(mock_targets.iter_targets(), genomes)
    assert (
        result == expected_answer
    )  # Length of intervals on chromosome1 and chromosome2


def test_sum_target_coverage_with_inf():
    targets = [
        TARGET_INTERVAL("chromosome1", 0, float("inf"), "+"),
        TARGET_INTERVAL("chromosome2", 0, float("inf"), "+"),
    ]
    result = sum_target_coverage(targets, genomes)
    assert result == 1000 + 2000  # Lengths of entire chromosome1 and chromosome2


@pytest.mark.parametrize(
    "targets_data, expected_answer", summary_test_data, indirect=["targets_data"]
)
def test_summary_percent_reference_covered(mock_aligner, mock_targets, expected_answer):
    genomes = get_contig_lengths(mock_aligner)
    ref_len = sum(genomes.values())
    with expected_answer as e:
        result = (
            _summary_percent_reference_covered(ref_len, mock_targets, genomes) * 100
        )
        assert result == pytest.approx(e)  # Expected result based on provided data
