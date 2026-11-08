from mlebench.grade_helpers import InvalidSubmissionError
from mlebench.clean_baseline_score import stanford_score


def grade(submission, answers):
    try:
        if not submission.columns.is_unique or not answers.columns.is_unique:
            raise ValueError("Duplicate columns")
        return stanford_score(submission.to_dict("records"), answers.to_dict("records"))
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidSubmissionError(str(error)) from error
