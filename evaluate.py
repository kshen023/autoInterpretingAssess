
import os
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# =========================================================
# 1. 文件路径和基本设置
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

SOURCE_FILE = BASE_DIR / "Source.txt"
REFERENCE_FILE = BASE_DIR / "Reference.txt"

INPUT_DIR = BASE_DIR / "Output"
CLEANED_DIR = BASE_DIR / "Cleaned"
RESULT_DIR = BASE_DIR / "Evaluation"

MODEL_NAME = "deepseek-flash"

# 已经生成评价的文件是否跳过
SKIP_EXISTING = True

# 每次 API 请求之间的间隔
REQUEST_INTERVAL = 1


# =========================================================
# 2. 连接 DeepSeek API
# =========================================================

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


# =========================================================
# 3. 读取 TXT 文件
# =========================================================

def read_text(file_path):

    encodings = [
        "utf-8-sig",
        "utf-8",
        "gb18030"
    ]

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


# =========================================================
# 4. 第一步：识别原文并提取学生口译
# =========================================================

EXTRACTION_PROMPT = """
You are an expert in bilingual speech transcription and interpreting.

You will receive two texts:

1. SOURCE TEXT:
The original speech delivered by the teacher.

2. FULL STUDENT TRANSCRIPT:
A transcription of a student's recording. It contains BOTH:
- The original source speech, which was played during the recording.
- The student's interpretation in the other language.

YOUR TASK:

Identify the source language by examining the SOURCE TEXT.

Then examine the FULL STUDENT TRANSCRIPT and separate the two parts.

Remove all content that corresponds to the SOURCE TEXT.

Keep ONLY the student's interpretation in the opposite language.

IMPORTANT RULES:

1. The source language may be English or Chinese.
   Do not assume that the source is always English.

2. The student's interpretation should normally be in the
   opposite language.

3. The source speech in the student transcript may not be
   exactly identical to the SOURCE TEXT because of speech
   recognition errors.

4. Use meaning and context to identify the source speech.
   Do not rely only on exact word matching.

5. Preserve the student's actual interpretation as faithfully
   as possible.

6. DO NOT correct grammar or vocabulary.

7. DO NOT summarize or rewrite the student's interpretation.

8. DO NOT remove repetitions, fillers, hesitation words,
   self-corrections, or incomplete sentences from the student's
   interpretation. These are important for fluency assessment.

9. If the student uses a few words from the source language
   within the interpretation, keep them if they are genuinely
   part of the student's interpretation.

10. If the student repeats part of the original source speech
    rather than interpreting it, remove that source portion.

11. Preserve the original order of the student's interpretation.

12. If the transcript contains multiple segments, preserve
    their order and, where possible, separate them with
    paragraph breaks.

13. If some content cannot be confidently classified, do not
    silently delete it. Keep it in the extracted interpretation
    and mention the uncertainty in extraction_notes.

OUTPUT:

Return a valid JSON object with exactly these fields:

{
  "source_language": "English or Chinese",
  "target_language": "Chinese or English",
  "student_interpretation": "The extracted student interpretation",
  "extraction_notes": "Briefly explain any uncertainty. If there
  is no uncertainty, write None."
}

Return JSON only. Do not include Markdown code fences.
"""


def extract_interpretation(student_id, source_text, full_transcript):

    user_prompt = f"""
STUDENT ID: {student_id}

SOURCE TEXT:

{source_text}


FULL STUDENT TRANSCRIPT:

{full_transcript}


Please identify and extract the student's interpretation
according to the instructions.
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,

        messages=[
            {
                "role": "system",
                "content": EXTRACTION_PROMPT
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],

        temperature=0.1,

        max_tokens=12000,

        stream=False,

        response_format={
            "type": "json_object"
        },

        extra_body={
            "thinking": {
                "type": "disabled"
            }
        }
    )

    result = response.choices[0].message.content

    data = json.loads(result)

    required_fields = [
        "source_language",
        "target_language",
        "student_interpretation",
        "extraction_notes"
    ]

    for field in required_fields:
        if field not in data:
            raise ValueError(
                f"提取结果缺少字段：{field}"
            )

    if not data["student_interpretation"].strip():
        raise ValueError(
            "没有提取到学生的口译内容，请检查原始转写稿。"
        )

    return data


# =========================================================
# 5. 第二步：根据三个维度评价学生口译
# =========================================================

ASSESSMENT_PROMPT = """
As an experienced university teacher of English-Chinese interpreting,
you are conducting formative assessments to help students improve.

You will receive:

1. The original SOURCE TEXT.
2. The REFERENCE TRANSLATION.
3. The STUDENT'S INTERPRETATION, which has already been separated
   from the original source speech.

Evaluate the student's interpretation according to three criteria.

CRITERION 1: INFORMATION COMPLETENESS

Evaluate whether the student has conveyed the original information
accurately and completely.

Identify:
- Omissions
- Inaccurate renditions
- Mistranslations
- Meaning distortions
- Incorrect numbers, names, and key details

Compare the student's interpretation with the source text
and the reference translation.

The reference translation is a guide, not the only acceptable
translation. Accept other accurate and natural expressions.

CRITERION 2: FLUENCY OF DELIVERY

Evaluate:
- Repetitions
- Filled pauses and fillers
- Hesitation
- Unnecessary self-corrections
- Incomplete sentences
- Disjointed expressions

Remember that this is a transcript rather than an audio recording.
Do not make unsupported claims about speaking speed, voice quality,
or the exact duration of pauses.

CRITERION 3: TARGET LANGUAGE QUALITY

Evaluate:
- Grammar
- Word choice
- Sentence structure
- Idiomatic expressions
- Clarity and naturalness

Identify specific examples from the student's actual interpretation.

GENERAL REQUIREMENTS:

- Include both strengths and weaknesses.
- Give specific and constructive suggestions.
- Use a friendly and encouraging tone.
- Do not invent mistakes.
- Do not penalize acceptable alternative translations.
- Do not confuse source speech with student interpretation.
- Divide the feedback according to the segments in the source text.
- Provide an improved version of the student's interpretation
  for each segment.
- The revised version should be accurate, natural, concise,
  and suitable for oral interpreting.

OUTPUT FORMAT:

Dear [Student ID],

Thank you for your hard work in interpreting the given passage.

Begin with a brief overall comment on the student's performance.

Then provide detailed feedback for each segment.

Segment 1:

Information completeness:
Discuss the accuracy and completeness of the student's interpretation.
Identify specific strengths, omissions, and inaccuracies.

Fluency of delivery:
Discuss repetitions, fillers, hesitation, and self-corrections.
Quote actual examples where appropriate.

Target language quality:
Discuss grammar, vocabulary, sentence structure, and naturalness.
Give specific examples.

Suggestions for improvement:
Give practical advice.

Revised interpretation:
Provide an improved version in the target language.

Repeat this structure for all remaining segments.

End with a short and encouraging concluding comment.

LANGUAGE:

Write the feedback mainly in Chinese.

Use Chinese or English as appropriate when quoting the student's
expressions and providing the revised interpretation.

If the source is English, the target interpretation will normally
be Chinese.

If the source is Chinese, the target interpretation will normally
be English.

Keep the feedback detailed, specific, and useful.
"""


def evaluate_student(
    student_id,
    source_text,
    reference_text,
    student_interpretation,
    source_language,
    target_language
):

    user_prompt = f"""
STUDENT ID: {student_id}

SOURCE LANGUAGE: {source_language}

TARGET LANGUAGE: {target_language}


SOURCE TEXT:

{source_text}


REFERENCE TRANSLATION:

{reference_text}


STUDENT'S INTERPRETATION:

{student_interpretation}


Please provide a detailed formative assessment.

Follow the required assessment criteria and output format.
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,

        messages=[
            {
                "role": "system",
                "content": ASSESSMENT_PROMPT
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],

        temperature=0.2,

        max_tokens=12000,

        stream=False,

        extra_body={
            "thinking": {
                "type": "disabled"
            }
        }
    )

    return response.choices[0].message.content


# =========================================================
# 6. 批量处理学生文件
# =========================================================

def main():

    print("=" * 60)
    print("English-Chinese Interpreting Assessment System")
    print("=" * 60)

    # 检查必要文件
    if not SOURCE_FILE.exists():
        raise FileNotFoundError("找不到 Source.txt！")

    if not REFERENCE_FILE.exists():
        raise FileNotFoundError("找不到 Reference.txt！")

    if not INPUT_DIR.exists():
        raise FileNotFoundError("找不到 Output 文件夹！")

    # 读取原文和参考译文
    source_text = read_text(SOURCE_FILE)
    reference_text = read_text(REFERENCE_FILE)

    # 创建输出文件夹
    CLEANED_DIR.mkdir(exist_ok=True)
    RESULT_DIR.mkdir(exist_ok=True)

    # 获取学生文件
    student_files = sorted(
        INPUT_DIR.glob("*.txt")
    )

    if not student_files:
        print("Output 文件夹中没有 TXT 文件。")
        return

    print(f"共找到 {len(student_files)} 份学生转写稿。")

    success = 0
    skipped = 0
    failed = 0

    # 逐份处理
    for index, file_path in enumerate(
        student_files,
        start=1
    ):

        # A6_转写.txt -> A6
        student_id = file_path.stem.split("_")[0]

        cleaned_file = (
            CLEANED_DIR /
            f"{student_id}_口译提取.txt"
        )

        evaluation_file = (
            RESULT_DIR /
            f"{student_id}_评价.txt"
        )

        print("\n" + "-" * 60)
        print(
            f"[{index}/{len(student_files)}] "
            f"正在处理学生：{student_id}"
        )

        # 已有评价时跳过
        if SKIP_EXISTING and evaluation_file.exists():
            print("已有评价结果，跳过。")
            skipped += 1
            continue

        try:

            # ---------------------------------------------
            # A. 读取完整学生转写稿
            # ---------------------------------------------

            full_transcript = read_text(file_path)

            if not full_transcript:
                raise ValueError("学生转写稿为空。")

            # ---------------------------------------------
            # B. 提取学生的实际口译
            # ---------------------------------------------

            print("第一步：正在识别并剔除原文……")

            extraction = extract_interpretation(
                student_id,
                source_text,
                full_transcript
            )

            student_interpretation = (
                extraction["student_interpretation"]
            )

            source_language = extraction["source_language"]
            target_language = extraction["target_language"]
            extraction_notes = extraction["extraction_notes"]

            # 保存提取后的口译
            cleaned_file.write_text(
                student_interpretation,
                encoding="utf-8"
            )

            print(
                f"原文语言：{source_language}"
            )

            print(
                f"目标语言：{target_language}"
            )

            print(
                f"口译内容已保存：{cleaned_file.name}"
            )

            if extraction_notes and extraction_notes != "None":
                print(
                    f"提取提示：{extraction_notes}"
                )

            # ---------------------------------------------
            # C. 评价学生口译
            # ---------------------------------------------

            print("第二步：正在生成评价……")

            feedback = evaluate_student(
                student_id,
                source_text,
                reference_text,
                student_interpretation,
                source_language,
                target_language
            )

            if not feedback:
                raise ValueError("评价结果为空。")

            # 保存评价
            evaluation_file.write_text(
                feedback,
                encoding="utf-8"
            )

            print(
                f"评价完成：{evaluation_file.name}"
            )

            success += 1

        except Exception as error:

            print(
                f"处理失败：{student_id}"
            )

            print(
                f"错误信息：{error}"
            )

            failed += 1

        time.sleep(REQUEST_INTERVAL)

    # =====================================================
    # 7. 输出统计信息
    # =====================================================

    print("\n" + "=" * 60)
    print("所有任务处理完毕！")
    print(f"成功评价：{success} 份")
    print(f"跳过文件：{skipped} 份")
    print(f"处理失败：{failed} 份")
    print(f"提取稿件：{CLEANED_DIR}")
    print(f"评价结果：{RESULT_DIR}")
    print("=" * 60)


# =========================================================
# 8. 启动程序
# =========================================================

if __name__ == "__main__":
    main()
