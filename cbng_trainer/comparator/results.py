def classification(result):
    return "Vandalism" if result.think_vandalism else "Constructive"


def hbool(result):
    return "Yes" if result else "No"


def generate_summary(results):
    markdown = '| Edit | Base | Target | Matches (Expected Match) |\n'
    markdown += '| ---- | ---- | ------ | ------------------------ |\n'
    for result in sorted(results, key=lambda r: r.enquiry.edit.id):
        markdown += f'| {result.enquiry.edit.id} '
        markdown += f'| {classification(result.base_result)}: {result.base_result.score} '
        markdown += f'| {classification(result.target_result)}: {result.target_result.score} '
        markdown += f'| {hbool(result.results_match)} ({hbool(result.expected_match)}) |\n'

    return markdown
