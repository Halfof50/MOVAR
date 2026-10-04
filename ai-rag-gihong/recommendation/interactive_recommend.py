# interactive_recommend.py
# 현재 추천 테스트용 (알레르기 부분 미구현)

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from recommendation.service.recommendation_service import (
    RecommendationService,
    print_result,
)

SYMPTOMS = [
    ("micro_keratin", "미세각질"),
    ("excess_sebum", "피지과다"),
    ("follicular_erythema", "모낭사이홍반"),
    ("follicular_pustule", "모낭홍반농포"),
    ("dandruff", "비듬"),
    ("hair_loss", "탈모"),
]


class QuitProgram(Exception):
    pass


def ask(prompt: str, allow_empty: bool = False) -> str:
    while True:
        value = input(prompt).strip()
        if value.lower() == "q":
            raise QuitProgram
        if value or allow_empty:
            return value
        print("값을 입력해주세요. (종료: q)")


def ask_level(label: str) -> int:
    while True:
        value = ask(f"{label} Level (0~3): ")
        try:
            level = int(value)
        except ValueError:
            print("0, 1, 2, 3 중 하나를 입력해주세요.")
            continue

        if level in (0, 1, 2, 3):
            return level
        print("0~3 범위로 입력해주세요.")


def ask_optional_int(prompt: str):
    while True:
        value = ask(prompt, allow_empty=True)
        if value == "":
            return None

        value = value.replace(",", "")
        try:
            number = int(value)
        except ValueError:
            print("숫자로 입력해주세요. 비워두면 미설정입니다.")
            continue

        if number < 0:
            print("0 이상의 값을 입력해주세요.")
            continue
        return number


def input_scalp_analysis() -> dict:
    print("\n" + "=" * 60)
    print("1. 두피 분석 결과 입력")
    print("각 증상을 0~3 단계로 입력하세요.")
    print("=" * 60)

    return {key: ask_level(label) for key, label in SYMPTOMS}


def input_user_profile() -> dict:
    print("\n" + "=" * 60)
    print("2. 사용자 정보 입력")
    print("필수가 아닌 항목은 Enter로 건너뛸 수 있습니다.")
    print("=" * 60)

    profile = {}

    age_group = ask(
        "연령대 (예: 20대, 30대 / 미입력 Enter): ",
        allow_empty=True,
    )
    if age_group:
        profile["age_group"] = age_group

    wash_frequency = ask(
        "머리 감는 주기 (예: 하루 1회, 이틀에 1회 / 미입력 Enter): ",
        allow_empty=True,
    )
    if wash_frequency:
        profile["wash_frequency"] = wash_frequency

    max_price = ask_optional_int(
        "희망 최대 가격 (예: 30000 / 미입력 Enter): "
    )
    if max_price is not None:
        profile["max_price"] = max_price

    return profile


def print_input_summary(scalp_analysis: dict, user_profile: dict):
    print("\n" + "-" * 60)
    print("입력 확인")

    symptom_text = ", ".join(
        f"{label} {scalp_analysis[key]}"
        for key, label in SYMPTOMS
    )
    print("두피 상태 :", symptom_text)

    if user_profile:
        print("사용자 정보:")
        for key, value in user_profile.items():
            print(f"  - {key}: {value}")
    else:
        print("사용자 정보: 없음")

    print("-" * 60)


def run_once(service: RecommendationService):
    scalp_analysis = input_scalp_analysis()
    user_profile = input_user_profile()
    print_input_summary(scalp_analysis, user_profile)

    while True:
        confirm = ask("\n이 정보로 추천을 실행할까요? (y/n, 종료 q): ").lower()
        if confirm in ("y", "yes"):
            break
        if confirm in ("n", "no"):
            print("\n입력을 취소했습니다.")
            return
        print("y 또는 n을 입력해주세요.")

    print("\n추천을 실행합니다...\n")

    result = service.recommend(
        scalp_analysis=scalp_analysis,
        user_profile=user_profile,
        use_llm=True,
    )

    print("\n" + "=" * 60)
    print("추천 결과")
    print("=" * 60)
    print_result(result)


def main():
    print("=" * 60)
    print("MOVAR 상품 추천 - 사용자 입력 테스트")
    print("어느 단계에서든 q 입력 시 종료")
    print("=" * 60)

    service = RecommendationService(backend="auto")

    while True:
        try:
            run_once(service)

            while True:
                again = ask(
                    "\n새로운 사용자로 다시 테스트할까요? "
                    "(y/n, 종료 q): "
                ).lower()

                if again in ("y", "yes"):
                    break
                if again in ("n", "no"):
                    print("\n프로그램을 종료합니다.")
                    return
                print("y 또는 n을 입력해주세요.")

        except QuitProgram:
            print("\n\nq 입력을 확인했습니다. 프로그램을 종료합니다.")
            return

        except KeyboardInterrupt:
            print("\n\nCtrl+C 입력을 확인했습니다. 프로그램을 종료합니다.")
            return

        except Exception as e:
            print("\n[추천 실행 오류]")
            print(f"{type(e).__name__}: {e}")

            try:
                retry = ask(
                    "\n처음부터 다시 입력하시겠습니까? "
                    "(y/n, 종료 q): "
                ).lower()
            except QuitProgram:
                print("\n프로그램을 종료합니다.")
                return

            if retry not in ("y", "yes"):
                print("\n프로그램을 종료합니다.")
                return


if __name__ == "__main__":
    main()
