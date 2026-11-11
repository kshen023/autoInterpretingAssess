
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


# ==========================================
# 1. 文件夹设置
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

INSTRUCTOR_DIR = BASE_DIR / "InstructorEvaluation"
AI_DIR = BASE_DIR / "Evaluation"

OUTPUT_FILE = BASE_DIR / "All_Evaluations.xlsx"


# ==========================================
# 2. 读取 TXT 文件
# ==========================================

def read_txt(file_path):

    encodings = ["utf-8-sig", "utf-8", "gb18030"]

    for encoding in encodings:
        try:
            return file_path.read_text(
                encoding=encoding
            ).strip()
        except UnicodeDecodeError:
            continue

    return "[无法读取文件，请检查编码]"


def get_student_id(file_path):
    """
    从文件名提取学生编号。
    例如：
    A6_评价.txt -> A6
    B2_评价.txt -> B2
    """

    return file_path.stem.split("_")[0]


def load_folder(folder):

    results = {}

    if not folder.exists():
        print(f"文件夹不存在：{folder}")
        return results

    for file_path in folder.glob("*.txt"):

        student_id = get_student_id(file_path)

        results[student_id] = read_txt(file_path)

    return results


# ==========================================
# 3. 读取两个文件夹
# ==========================================

print("正在读取教师评价……")
instructor_data = load_folder(INSTRUCTOR_DIR)

print("正在读取 AI 评价……")
ai_data = load_folder(AI_DIR)

# 合并所有学生编号
all_students = sorted(
    set(instructor_data.keys()) |
    set(ai_data.keys())
)

print(f"共找到 {len(all_students)} 名学生。")


# ==========================================
# 4. 创建 Excel
# ==========================================

wb = Workbook()
ws = wb.active
ws.title = "Evaluation Comparison"

# 表头
headers = [
    "Student ID",
    "Instructor Evaluation",
    "AI Evaluation"
]

ws.append(headers)


# ==========================================
# 5. 写入学生评价
# ==========================================

for student_id in all_students:

    instructor_text = instructor_data.get(
        student_id,
        "No instructor evaluation"
    )

    ai_text = ai_data.get(
        student_id,
        "No AI evaluation"
    )

    ws.append([
        student_id,
        instructor_text,
        ai_text
    ])


# ==========================================
# 6. 设置 Excel 格式
# ==========================================

# 表头样式
header_fill = PatternFill(
    fill_type="solid",
    fgColor="4472C4"
)

header_font = Font(
    bold=True,
    color="FFFFFF",
    size=12
)

for cell in ws[1]:

    cell.fill = header_fill
    cell.font = header_font

    cell.alignment = Alignment(
        horizontal="center",
        vertical="center"
    )


# 设置列宽
ws.column_dimensions["A"].width = 15
ws.column_dimensions["B"].width = 65
ws.column_dimensions["C"].width = 65

# 设置正文样式
for row in ws.iter_rows(min_row=2):

    for cell in row:

        cell.alignment = Alignment(
            horizontal="left",
            vertical="top",
            wrap_text=True
        )

        cell.font = Font(
            name="Arial",
            size=10
        )

# 学生编号列居中
for cell in ws["A"][1:]:

    cell.alignment = Alignment(
        horizontal="center",
        vertical="top"
    )

# 设置边框
thin_border = Border(
    left=Side(style="thin", color="D9E1F2"),
    right=Side(style="thin", color="D9E1F2"),
    top=Side(style="thin", color="D9E1F2"),
    bottom=Side(style="thin", color="D9E1F2")
)

for row in ws.iter_rows():

    for cell in row:
        cell.border = thin_border


# 设置行高
ws.row_dimensions[1].height = 30

for row_num in range(2, ws.max_row + 1):
    ws.row_dimensions[row_num].height = 150


# 冻结首行和学生编号列
ws.freeze_panes = "B2"

# 开启筛选
ws.auto_filter.ref = ws.dimensions


# ==========================================
# 7. 保存 Excel
# ==========================================

wb.save(OUTPUT_FILE)

print("\n" + "=" * 45)
print("Excel 整合完成！")
print(f"学生人数：{len(all_students)}")
print(f"保存位置：{OUTPUT_FILE}")
print("=" * 45)
