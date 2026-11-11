
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# ==========================================
# 1. 文件夹及 API 配置
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

# 输入：原来的详细评价
INPUT_DIR = BASE_DIR / "Evaluation"

# 输出：教师风格的简化评价
OUTPUT_DIR = BASE_DIR / "InstructorEvaluation"

MODEL_NAME = "deepseek-flash"

# 是否跳过已经生成的文件
SKIP_EXISTING = True

# 每处理一名学生后暂停1秒
REQUEST_INTERVAL = 1


# ==========================================
# 2. 连接 DeepSeek API
# ==========================================

load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise ValueError(
        "没有找到 DeepSeek API Key，请检查 .env 文件。"
    )

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
    timeout=180.0,
    max_retries=3
)


# ==========================================
# 3. 读取 TXT 文件
# ==========================================

def read_text(file_path):

    encodings = ["utf-8-sig", "utf-8", "gb18030"]

    for encoding in encodings:
        try:
            return file_path.read_text(
                encoding=encoding
            ).strip()

        except UnicodeDecodeError:
            continue

    raise ValueError(
        f"无法读取文件：{file_path.name}"
    )


# ==========================================
# 4. 教师简评生成要求
# ==========================================

INSTRUCTOR_PROMPT = """
You are an experienced university interpreting instructor.

You will receive a detailed AI-generated assessment of a
student's English-Chinese or Chinese-English interpreting
performance.

Your task is to rewrite this assessment into a much shorter,
simpler, and more concise version that resembles routine
teacher feedback.

IMPORTANT:
This is NOT a new detailed assessment.
You must summarize the existing assessment rather than
conducting another comprehensive evaluation.

The feedback must cover exactly THREE aspects:

1. Information Completeness
Briefly comment on whether the student has conveyed the
main ideas and important information accurately.
Mention major omissions or inaccuracies only when relevant.

2. Fluency of Delivery
Briefly comment on repetitions, hesitation, self-correction,
or overall continuity based on the available transcript.
Do not invent information about speaking speed, pauses,
or voice quality.

3. Target Language Quality
Briefly comment on grammar, vocabulary, sentence structure,
and naturalness. Focus only on the most important issues.

WRITING REQUIREMENTS:

- Keep the entire feedback approximately 150 words.
- Do not exceed 200 words.
- Be concise, direct, and practical.
- Use a natural, professional teacher-like tone.
- Do not write lengthy explanations.
- Do not analyze every individual segment.
- Do not provide a revised or model translation.
- Do not repeat the detailed suggestions in the original assessment.
- Select only the most important strengths and weaknesses.
- Do not invent errors or criticisms.
- If the original assessment identifies a strength,
  retain it where appropriate.
- Avoid exaggerated praise or overly formal academic language.
- Make the feedback noticeably shorter and less detailed
  than the original assessment.
- You must write the feedback in Chinese unless you are quoting English sources or English translation from students.

Use the following format:

Dear [Student ID],

Information Completeness:
[Brief comment.]

Fluency of Delivery:
[Brief comment.]

Target Language Quality:
[Brief comment.]

Overall Comment:
[One or two concise sentences of encouragement
and a practical suggestion for improvement.]

Do not add any extra sections.
"""


# ==========================================
# 5. 调用 DeepSeek 生成教师简评
# ==========================================

def generate_instructor_feedback(student_id, detailed_feedback):

    user_prompt = f"""
STUDENT ID: {student_id}

DETAILED ASSESSMENT:

{detailed_feedback}

Please rewrite the assessment into a concise
teacher-style feedback report following the instructions.
"""

    response = client.chat.completions.create(

        model=MODEL_NAME,

        messages=[
            {
                "role": "system",
                "content": INSTRUCTOR_PROMPT
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],

        temperature=0.3,

        max_tokens=1000,

        stream=False,

        extra_body={
            "thinking": {
                "type": "disabled"
            }
        }
    )

    return response.choices[0].message.content.strip()


# ==========================================
# 6. 批量处理所有学生
# ==========================================

def main():

    print("=" * 60)
    print("Instructor Feedback Generation System")
    print("=" * 60)

    # 检查输入文件夹
    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            "找不到 Evaluation 文件夹！"
        )

    # 创建输出文件夹
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 获取所有 TXT 文件
    student_files = sorted(
        INPUT_DIR.glob("*.txt")
    )

    if not student_files:
        print("Evaluation 文件夹中没有 TXT 文件。")
        return

    print(
        f"共找到 {len(student_files)} 份详细评价。"
    )

    success = 0
    skipped = 0
    failed = 0

    # 逐个处理学生
    for index, file_path in enumerate(
        student_files, start=1
    ):

        # 提取学生编号
        student_id = file_path.stem.split("_")[0]

        # 设置输出文件名
        output_file = OUTPUT_DIR / (
            f"{student_id}_教师简评.txt"
        )

        print(
            f"\n[{index}/{len(student_files)}] "
            f"正在处理：{student_id}"
        )

        # 如果已经存在，直接跳过
        if SKIP_EXISTING and output_file.exists():

            print("已有简评，跳过。")
            skipped += 1
            continue

        try:

            # 读取原来的详细评价
            detailed_feedback = read_text(file_path)

            if not detailed_feedback:
                raise ValueError("原评价文件为空。")

            print("正在生成教师简评……")

            # 调用 DeepSeek
            instructor_feedback = (
                generate_instructor_feedback(
                    student_id,
                    detailed_feedback
                )
            )

            if not instructor_feedback:
                raise ValueError("生成的简评为空。")

            # 保存结果
            output_file.write_text(
                instructor_feedback,
                encoding="utf-8"
            )

            print(
                f"完成：{output_file.name}"
            )

            success += 1

        except Exception as error:

            print(f"处理失败：{student_id}")
            print(f"错误信息：{error}")

            failed += 1

        time.sleep(REQUEST_INTERVAL)

    # ======================================
    # 7. 处理结果统计
    # ======================================

    print("\n" + "=" * 60)
    print("所有任务处理完毕！")

    print(f"成功生成：{success} 份")
    print(f"跳过文件：{skipped} 份")
    print(f"处理失败：{failed} 份")

    print(f"输出文件夹：{OUTPUT_DIR}")

    print("=" * 60)


if __name__ == "__main__":
    main()
