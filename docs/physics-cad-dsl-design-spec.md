# 물리역학 검증 내장 3D CAD DSL — 설계 참고 문서

> 목적: Lean 스타일의 정적 검증과 3D CAD 기하 모델링, CAE 물리 해석을 하나의 언어로 통합하는
> 새로운 DSL의 문법·아키텍처 설계를 위한 참고 자료 및 핵심 기능 명세.

---

## 1. 문제 정의

기존 CAD/CAE 워크플로우의 구조적 한계:

- **디자인–해석 이원화**: CAD 모델링 후 별도의 CAE 해석 단계에서 오류를 발견. 피드백 루프가 느리고 사람 손을 거침
- **바이너리 파일 기반**: Git 등 버전 관리가 사실상 불가능, 파라미터 변경 시 자동 재검증 불가
- **런타임에서만 실패 발견**: 규격 미달, 조립 불가, 물리 한계 초과가 설계 단계에서 걸러지지 않음

**목표**: "코드로 정의하고, 수학적으로 증명하며, 물리적으로 검증한다."
컴파일 성공 = 기하학적 정합성 + 물리적 안전성이 보장된 설계.

---

## 2. 전체 아키텍처 — 3-커널 구조

```
┌─────────────────────────────────────────────┐
│  Front-end : 타입/증명 커널 (Lean-like)       │
│  치수 제약, 조립 정합성, 물리 한계의 정적 증명   │
├─────────────────────────────────────────────┤
│  Middle-end : 기하 커널 (OpenCASCADE)        │
│  B-Rep/CSG 형상 생성, 토폴로지 관리, STEP 출력 │
├─────────────────────────────────────────────┤
│  Back-end : 물리 커널 (CAE)                  │
│  메싱(Gmsh) → FEA/CFD 수치 해석 → 결과 회수   │
└─────────────────────────────────────────────┘
```

| 계층 | 역할 | 핵심 참고 대상 |
|---|---|---|
| Front-end | 종속 타입 기반 제약 선언·증명 | Lean 4, Idris 2, F* (+Z3) |
| Middle-end | 형상 생성·연산·입출력 | OpenCASCADE(OCP), CadQuery, Fornjot |
| Back-end | 메싱·수치 해석 | Gmsh/Netgen, CalculiX, FEniCS, OpenFOAM |

---

## 3. 언어 코어에 반드시 포함되어야 할 중심 기능

### 3.1 물리량 단위 타입 시스템 (Dimensional Types)

- `276MPa`, `2.7g/cm³`, `2000N` 등 모든 물리량이 **단위를 포함한 타입**
- 차원이 맞지 않는 연산(`Force + Length`)은 컴파일 에러
- 단위 환산(`mm ↔ m`, `MPa ↔ Pa`)은 타입 시스템이 자동 처리
- 참고: Idris 2의 타입 수준 물리량, F#의 units of measure

```
material Aluminum6061 {
    density        : 2.7 g/cm³,
    yield_strength : 276 MPa,
    elastic_modulus: 68.9 GPa
}
```

### 3.2 종속 타입 기반 형상 제약 (Dependent / Refinement Types)

- 제약 조건의 **증명 없이는 형상 생성 자체가 타입 에러**가 되는 구조

```
-- 두께 5mm 이상이라는 증명(h_proof)이 있어야만 생성 가능한 타입
shape Bracket (thickness : Real) (h_proof : thickness >= 5.0) {
    material : Aluminum6061,
    let base = Box(100, 50, thickness),
    let hole = Cylinder(radius = 10, height = thickness + 2),
    geometry = base - hole.translate(x = 50, y = 25, z = -1)
}
```

적용 범위:
- **조립 정합성**: `A.hole_radius == B.pin_radius` 불성립 시 컴파일 에러
- **공차 분석**: 치수에 공차(Tolerance)를 종속 유형으로 부착, 최악 공차 조합에서도 조립 가능함을 판별

### 3.3 기하학적 셀렉터 문법 — Persistent Naming 문제의 언어적 해결 ★

**언어 정체성을 결정하는 최우선 설계 항목.**

- 문제: OpenCASCADE는 파라미터 변경 후 재생성 시 토폴로지 ID(`Face 3` 등)의 유지를
  보장하지 않음 (Persistent Naming Problem). 인덱스 참조 방식은 경계 조건을 파괴함
- 해결: CadQuery의 셀렉터 방식을 **1급 문법**으로 내장

```
fix   : faces(">Z")          -- Z축 최상단 면
force : 2000N on faces("<X")  -- X축 최소 방향 면
```

- 의미론적/기하학적 셀렉터(방향, 최대/최소, 태그 기반)만이 파라메트릭 변경 후에도
  경계 조건 참조를 안정적으로 유지

### 3.4 전역화된 CSG 연산 (Total CSG)

- 문제: 문법상 합법인 `A - B`도 면이 미세하게 겹치면 커널 불리언 연산이 크래시
- 해결: 연산의 **성공 사전 조건을 타입으로 증명**해야 연산 가능

```
-- 타공 실린더 반지름이 판재 경계를 침범하지 않음을 증명해야 컴파일 통과
constraint : cylinder.radius < board.width / 2
```

- 실패 가능한 부분 함수(partial)를 증명 조건이 붙은 전역 함수(total)로 승격

### 3.5 경계 조건의 1급 선언 (Boundary Conditions as First-class)

- 하중·고정·접촉 조건이 형상 코드와 함께 텍스트로 버전 관리되는 스펙

```
boundary_condition StaticLoad {
    target : Bracket,
    fix    : faces("<X"),
    force  : Force(2000N) on faces(">X")
}
```

### 3.6 검증 의미론 — 물리 검증을 수학적 증명처럼 다루는 3계층 전략 ★

완벽한 100% 매핑은 불가능(연속 물리의 이산화 오차)하나, 아래 3계층으로
**"컴파일 타임에 안전함이 보장되는" 사용자 경험**은 달성 가능.

#### 계층 1 — 폐형식 해석 증명 (Analytical, 순수 증명)
- 보(Beam) 공식, 응력·토크 공식 등 닫힌 형태(closed-form) 방정식을 언어 내부에 구현
- 시뮬레이션 없이 순수 수학 증명으로 처리. 가장 빠르고 가장 엄밀
- 이 단계에서 걸러지면 솔버 구동 자체가 불필요

#### 계층 2 — 보수적 바운딩 (Interval Arithmetic / Verified Numerics)
- 해석 결과를 단일값이 아닌 **구간 `[하한, 상한]`**으로 산출
- `상한 < yield_strength` 형태로 안전성을 보수적으로 증명
- 요건: 엄밀한 상·하한 계산이 가능한 Verified Numerics 기반 특수 솔버
- 비선형 제약은 dReal의 δ-completeness(δ-완전성) 방식으로 반례 부재를 탐색

#### 계층 3 — 신뢰 오라클 (Trusted Backend Oracle)
- 외부 FEA 솔버(CalculiX 등)를 `axiom`으로 선언, 결과를 무조건 신뢰

```
axiom run_fea_solver (shape : CADShape) (load : Force) : PhysicalResult

theorem bracket_is_safe :
    (run_fea_solver my_bracket 2000N).max_stress < 276MPa :=
by
    evaluate_external_solver  -- 컴파일 타임에 솔버 실제 구동
```

- 엄밀한 증명은 아니지만, "컴파일 시 물리 해석이 자동으로 돌고 기준 초과 시
  컴파일 에러"라는 점에서 정적 타입 검증과 동일한 UX

#### 문법 노출 방식 — 증명 전술(Tactic)의 계층화

```
by solve_analytical     -- 계층 1: 폐형식 수식 증명
by solve_fea_bounds     -- 계층 2: 구간 바운딩 증명
by trust_oracle         -- 계층 3: 외부 솔버 오라클
```

계층이 낮을수록 엄밀하고, 높을수록 표현력이 넓음. 사용자가 신뢰 수준을 명시적으로 선택.

### 3.7 컴파일 타임 솔버-인-더-루프 (Solver-in-the-Loop)

- "컴파일"의 의미를 확장: 파싱·타입체크 → 형상 생성 → 메싱 → 해석 → 결과 회수 → 판정
- Lean 4의 매크로/elaborator가 컴파일 중 I/O로 외부 프로세스를 호출하는 메커니즘 활용
- CI/CD 파이프라인에서 파라미터 변경 → 자동 재검증이 자연스럽게 성립

---

## 4. 계층별 참고 프로젝트 리스트

### 4.1 언어 설계·증명 시스템

| 프로젝트 | 참고 포인트 |
|---|---|
| **Lean 4** | 가장 유력한 호스트 언어. 매크로 시스템으로 eDSL 임베딩, elaborator로 컴파일 타임 I/O |
| **Idris 2** | 실행 가능한 소프트웨어 지향 종속 타입. 물리량·치수의 타입 수준 처리 |
| **F\* (+Z3)** | SMT 솔버 백엔드 정적 검증. 기하 제약("구멍이 경계 내부에 존재")의 자동 판별 모델 |
| **dReal** | δ-completeness. 고차 비선형 공학 수식의 반례 탐색 |

### 4.2 Code-CAD / 기하 커널

| 프로젝트 | 참고 포인트 |
|---|---|
| **OpenCASCADE (OCCT)** | 산업 표준 B-Rep 커널. Booleans(`Fuse/Cut/Common`), STEP/IGES 입출력(`STEPControl_*`) |
| **CadQuery / OCP** | OCCT의 Python 래핑 구조, **셀렉터 설계**(`faces(">Z")`). 소스 분석이 실질적 첫걸음 |
| **OpenSCAD** | 함수형 Code-CAD 문법의 직관. 원조 격 |
| **Fornjot (fj)** | Rust 기반 모던 커널 아키텍처. 자체 커널 구축 시 참고 |

### 4.3 CAE / 물리 해석

| 프로젝트 | 참고 포인트 |
|---|---|
| **CalculiX** | Abaqus 호환 `.inp` 포맷 — DSL 컴파일러의 자동 생성 타겟. 구조·열 해석 |
| **Gmsh / Netgen** | STEP → 해석용 사면체 메시 파이프라인. OCCT 자체 메싱(BRepMesh)은 해석용 품질 부족 |
| **FEniCS** | PDE ↔ 코드 자동 매핑. 수학적 명제와 물리 해석 사이의 다리 연구 |
| **OpenFOAM** | CFD 검증이 필요할 경우의 사실상 표준 |

### 4.4 학술 연구·유사 시도

| 프로젝트/주제 | 참고 포인트 |
|---|---|
| **Penrose (CMU)** | 제약 조건 기반 기하 구조 자동 배치 아키텍처 |
| **Julia SciML** | 미분 가능 프로그래밍으로 설계 변수(CAD)와 물리 방정식(CAE)을 결합해 최적화 |
| **POPL/PLDI 계열 논문** | "Types for Geometric Programming", "Verified CAD Modeling" 키워드 |

---

## 5. 알려진 난제와 대응 전략

| 난제 | 내용 | 대응 |
|---|---|---|
| **Persistent Naming** | 재생성 시 토폴로지 ID 비결정성 → 경계 조건 참조 붕괴 | 셀렉터 문법을 1급으로 내장 (§3.3) |
| **불리언 연산 실패** | 면 겹침·공차 문제로 커널 크래시 | 사전 조건 증명 필수화 — Total CSG (§3.4) |
| **연속 물리 ↔ 이산 논리 간극** | FEM은 근사·오차 내재, Lean은 기호 논리 | 3계층 검증 전략 (§3.6) |
| **OCCT 직접 제어 난이도** | C++ 레거시, 바인딩 복잡 | 프로토타입은 OCP(Python) 경유, 장기적으로 Rust 바인딩 검토 |

---

## 6. 권장 프로토타입 파이프라인

```
[1] Lean 4 eDSL          형상·재료·제약 선언, 계층 1 증명 (폐형식 수식)
        │  AST/IR export
        ▼
[2] Python + CadQuery/OCP  B-Rep 생성, 불리언 연산, STEP 파일 출력
        │  STEP
        ▼
[3] Gmsh                  해석용 메시 생성
        │  mesh + BC
        ▼
[4] CalculiX (.inp 자동 생성)  FEA 해석 실행
        │  max_stress 등 결과 파싱
        ▼
[5] Lean 오라클로 반환      계층 2/3 판정 → 컴파일 성공(green) / 실패(red)
```

**첫 실행 과제**: CadQuery가 OCP로 OpenCASCADE를 래핑하고 셀렉터를 구현한
소스 코드 분석 → 셀렉터 의미론을 자체 DSL 문법으로 재설계.

---

## 7. 설계 우선순위 요약

언어의 정체성을 결정하는 3대 요소:

1. **셀렉터 문법** (§3.3) — 경계 조건 안정성의 전제. 이것이 없으면 파라메트릭 검증 자체가 불성립
2. **검증 전술 계층** (§3.6) — analytical / bounds / oracle의 3단 구조가 이 언어만의 차별점
3. **단위 타입 시스템** (§3.1) — 물리 검증 언어의 기본 위생

CSG 연산·경계 조건 선언 문법(§3.4, §3.5)은 기존 Code-CAD(CadQuery, OpenSCAD)
문법을 차용해도 무방. 혁신 리소스는 위 3가지에 집중할 것.
