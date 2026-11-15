import pandas
import re

def add_virtual_column(df: pandas.DataFrame, role: str, new_column: str) -> pandas.DataFrame:
    name = r"[A-Za-z_]+"

    # check name correctness
    is_name_incorrect = not new_column or re.search(r"[^A-Za-z_]", new_column)
    if is_name_incorrect:
        return pandas.DataFrame()

    # check expression correctness
    is_expression_correct = re.fullmatch(rf"\s*{name}(\s*[+\-*]\s*{name})*\s*", role)
    if not is_expression_correct:
        return pandas.DataFrame()

    # check column existence
    used_columns = re.findall(name, role)
    are_columns_missing = any(column not in df.columns for column in used_columns)
    if are_columns_missing:
        return pandas.DataFrame()

    # add virtual column
    # backticks make pandas read every name as a column, never as a Python keyword or literal (True, and, not)
    quoted_role = re.sub(name, lambda match: f"`{match.group()}`", role)
    df_res = df.copy()
    df_res[new_column] = df_res.eval(quoted_role)
    return df_res

    

    


