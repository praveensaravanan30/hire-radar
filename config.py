"""
Job tracker configuration.

Structure:
  TRACKS  — two top-level tracks (AI, HW), each with sub-roles
  COMPANIES — curated target companies per track, split into tiers
"""

# ---------------------------------------------------------------------------
# TRACKS — role definitions
# Each role has:
#   label          display name
#   aliases        fuzzy-match keywords the user can type
#   keyword_groups clusters of ATS terms; query_builder combines these
#   must_have_any  pre-filter: job text must contain at least one of these
#   scoring_context  LLM prompt context for this specific role
# ---------------------------------------------------------------------------

TRACKS = {
    "AI": {
        "label": "AI / Software Track",
        "resume": "../AI/Praveen_Saravanan_Resume.pdf",
        "roles": {
            "AI_INFRA": {
                "label": "AI Infrastructure Engineer",
                "aliases": [
                    "ai", "ai infra", "ai infrastructure", "llm", "agent infra",
                    "eval", "evaluation", "ml infra", "inference infra",
                ],
                "keyword_groups": {
                    "titles": [
                        "AI Infrastructure Engineer",
                        "ML Infrastructure Engineer",
                        "LLM Evaluation Engineer",
                        "AI Platform Engineer",
                        "Agent Infrastructure Engineer",
                    ],
                    "domains": ["LLM", "evaluation pipeline", "RL training", "agent evaluation", "inference"],
                    "tools":   ["PyTorch", "Docker", "GCP", "Modal", "ONNX", "Ray", "Triton"],
                    "concepts":["synthetic data", "reward modeling", "model evaluation", "benchmarking"],
                },
                "must_have_any": [
                    "AI infrastructure", "ML infrastructure", "LLM", "agent evaluation",
                    "evaluation pipeline", "synthetic data", "RL training", "model evaluation",
                    "inference infrastructure", "MLOps", "AI/ML", "machine learning",
                    "foundation model", "large language model",
                ],
                "scoring_context": """
Candidate: Praveen Saravanan — AI Infrastructure Engineer
Core strengths:
- Closed-loop evaluation infrastructure for RL agent training (Docker, GCP, Modal)
- Automated grading/scoring pipelines for AI agent tasks (Python, cocotb, Yosys)
- LLM-based RTL mutation pipeline for synthetic training data (Claude API)
- Edge model optimization: INT8 quantization, pruning, ONNX export (PyTorch, ARM/CUDA)
- Unique edge: deep hardware background (GPU RTL @ Samsung, FPGA @ UF) + AI infra
Tools: PyTorch, ONNX, TensorFlow, Docker, GCP, Modal, Python, C++
Target: AI infra, evaluation engineering, agent infra, LLM tooling, ML platform.
Ideal employers: Frontier AI labs, AI-native startups, GPU/chip companies with AI divisions.
""",
            },

            "ML_PLATFORM": {
                "label": "ML Platform / MLOps Engineer",
                "aliases": [
                    "mlops", "ml platform", "ml engineering", "platform engineer",
                    "ml engineer", "data platform",
                ],
                "keyword_groups": {
                    "titles": [
                        "ML Platform Engineer",
                        "MLOps Engineer",
                        "Machine Learning Engineer",
                        "AI Platform Engineer",
                    ],
                    "domains": ["MLOps", "model serving", "training pipeline", "feature store", "data pipeline"],
                    "tools":   ["Kubernetes", "Airflow", "MLflow", "Kubeflow", "Spark", "Ray", "Docker"],
                    "concepts":["model deployment", "CI/CD", "experiment tracking", "data versioning"],
                },
                "must_have_any": [
                    "MLOps", "ML platform", "machine learning", "model deployment",
                    "training pipeline", "model serving", "feature store", "AI/ML",
                ],
                "scoring_context": """
Candidate: Praveen Saravanan — ML Platform / MLOps Engineer
Core strengths:
- Built evaluation + grading infrastructure for AI agent pipelines (Docker, GCP, Modal)
- Automated data pipelines for LLM training data generation
- Experience with containerized ML workloads, cloud infra (GCP), Python tooling
- Hardware intuition: understands compute bottlenecks at silicon level (GPU/FPGA background)
Tools: Python, Docker, GCP, Modal, PyTorch, ONNX
Target: ML platform, MLOps, model serving infra, training pipeline engineering.
""",
            },
        },
    },

    "HW": {
        "label": "Hardware Track",
        "resume": "../RTL/Praveen_Saravanan_Resume.pdf",
        "roles": {
            "RTL": {
                "label": "RTL Design Engineer",
                "aliases": [
                    "rtl", "rtl design", "digital design", "hardware design",
                    "asic design", "chip design", "rtl engineer",
                ],
                "keyword_groups": {
                    "titles": [
                        "RTL Design Engineer",
                        "Digital Design Engineer",
                        "Hardware Design Engineer",
                        "ASIC RTL Engineer",
                        "Chip Design Engineer",
                    ],
                    "chips":   ["CPU", "GPU", "SoC", "mobile", "datacenter", "NPU"],
                    "tools":   ["SystemVerilog", "Verilog", "Synopsys", "Cadence", "Design Compiler"],
                    "concepts":["RTL", "synthesis", "timing closure", "PPA", "microarchitecture", "lint CDC"],
                },
                "must_have_any": [
                    "RTL", "Verilog", "SystemVerilog", "ASIC", "digital design",
                    "hardware design", "chip design", "synthesis", "VLSI",
                ],
                "scoring_context": """
Candidate: Praveen Saravanan — RTL / Digital Design Engineer
Core strengths:
- GPU RTL Design Intern @ Samsung: GE subsystem for next-gen mobile GPU (spec→RTL→PD handoff)
  Tools: Synopsys VCS, Verdi, Design Compiler, VC Spyglass (lint, CDC/RDC)
- FPGA security RTL @ UF: multi-tenant cloud FPGA (secure boot, bitstream encryption)
- RTL synthesis/sim pipelines @ Phinity Labs (Yosys, OpenSTA, cocotb)
- Projects: 5-stage RISC-V pipeline (RV32I), UVM DV of digital calculator
Skills: Verilog/SystemVerilog, Synopsys VCS/Verdi/DC, Xilinx Vivado, PPA analysis
Target: RTL design, SoC, GPU/CPU hardware engineering roles.
""",
            },

            "DV": {
                "label": "Design Verification (DV) Engineer",
                "aliases": [
                    "dv", "verification", "design verification", "uvm",
                    "functional verification", "hw verification", "hardware verification",
                ],
                "keyword_groups": {
                    "titles": [
                        "Design Verification Engineer",
                        "DV Engineer",
                        "Hardware Verification Engineer",
                        "Functional Verification Engineer",
                        "RTL Verification Engineer",
                    ],
                    "chips":   ["CPU", "GPU", "SoC", "ASIC", "mobile"],
                    "methods": ["UVM", "functional verification", "formal verification", "coverage"],
                    "tools":   ["SystemVerilog", "cocotb", "Synopsys VCS", "Cadence", "Jaspergold"],
                },
                "must_have_any": [
                    "verification", "DV", "UVM", "SystemVerilog", "testbench",
                    "functional verification", "formal verification", "RTL verification",
                    "coverage", "cocotb", "hardware verification",
                ],
                "scoring_context": """
Candidate: Praveen Saravanan — Design Verification (DV) Engineer
Core strengths:
- UVM-based verification of digital calculator RTL (Cadence Jaspergold, coverage analysis)
- Verification pipelines @ Phinity Labs: cocotb-based sim for HW agent evaluation (correctness, area, power)
- 5-stage RISC-V processor: verified with random testbenches + RISC-V benchmark suite
- LLM bug injection pipeline: generated + screened synthetic RTL bugs with cocotb
- FPGA security validation @ UF: ProVerif, secure boot, bitstream encryption verification
Skills: SystemVerilog, UVM, cocotb, Synopsys VCS/Verdi, Cadence Jaspergold
Target: DV, functional verification, coverage-driven verification, formal verification roles.
""",
            },

            "PERF": {
                "label": "CPU/GPU Performance Modeling Engineer",
                "aliases": [
                    "perf", "performance", "performance modeling", "cpu modeling",
                    "gpu performance", "cpu performance", "performance analysis",
                    "performance engineer", "perf model",
                ],
                "keyword_groups": {
                    "titles": [
                        "CPU Performance Engineer",
                        "Performance Modeling Engineer",
                        "GPU Performance Engineer",
                        "Processor Performance Analyst",
                        "Performance Analysis Engineer",
                    ],
                    "chips":   ["CPU", "GPU", "Arm", "RISC-V", "x86", "NPU"],
                    "tools":   ["gem5", "cycle-accurate simulator", "performance simulator", "DRAMsim"],
                    "concepts":["IPC", "cache hierarchy", "memory bandwidth", "pipeline", "bottleneck analysis",
                                "workload characterization", "microarchitecture"],
                },
                "must_have_any": [
                    "performance modeling", "performance simulation", "cycle-accurate",
                    "CPU performance", "GPU performance", "gem5", "IPC", "workload analysis",
                    "performance analysis", "microarchitecture simulation",
                ],
                "scoring_context": """
Candidate: Praveen Saravanan — CPU/GPU Performance Modeling Engineer
Core strengths:
- 5-stage RISC-V processor (RV32I) with hazard detection, forwarding, branch prediction — understands pipeline perf
- GPU RTL @ Samsung: GE subsystem, PPA analysis, timing — silicon-level performance intuition
- Coursework: Parallel Computer Architecture, Advanced Digital Design
- gem5 listed in skills (performance simulation)
- Experience analyzing area/power/timing tradeoffs from synthesis results
Target: CPU/GPU performance modeling, microarchitecture analysis, workload characterization.
Note: This is a stretch role — emphasize architecture coursework, RISC-V project, and PPA experience.
""",
            },

            "UARCH": {
                "label": "Microarchitecture Engineer",
                "aliases": [
                    "uarch", "microarchitecture", "micro arch", "processor design",
                    "cpu architect", "cpu design", "microarch", "processor architect",
                ],
                "keyword_groups": {
                    "titles": [
                        "Microarchitecture Engineer",
                        "CPU Microarchitecture Engineer",
                        "Processor Design Engineer",
                        "CPU Architect",
                        "Hardware Architect",
                    ],
                    "chips":   ["CPU", "GPU", "NPU", "Arm", "RISC-V", "x86"],
                    "concepts":["microarchitecture", "pipeline", "out-of-order", "branch prediction",
                                "cache coherence", "memory subsystem", "ISA"],
                    "tools":   ["RTL", "SystemVerilog", "gem5", "Verilog"],
                },
                "must_have_any": [
                    "microarchitecture", "CPU design", "processor design", "pipeline",
                    "out-of-order", "branch prediction", "cache", "ISA", "RISC-V",
                    "computer architecture", "hardware architect",
                ],
                "scoring_context": """
Candidate: Praveen Saravanan — Microarchitecture Engineer
Core strengths:
- Designed 5-stage RISC-V pipeline (RV32I): hazard detection, data forwarding, branch prediction
- GPU RTL @ Samsung: deep familiarity with GPU microarchitecture (GE subsystem)
- Coursework: Parallel Computer Architecture, cache coherence (MESI/MOESI), PCIe, AMBA AXI
- Understands PPA tradeoffs from synthesis experience
Target: CPU/GPU microarchitecture, processor design, hardware architect roles.
Note: Strongest angle is RISC-V pipeline + Samsung GPU internals + architecture coursework.
""",
            },

            "SOC": {
                "label": "SoC / ASIC Design Engineer",
                "aliases": [
                    "soc", "asic", "system on chip", "soc design", "asic design",
                    "soc engineer", "asic engineer", "soc integration",
                ],
                "keyword_groups": {
                    "titles": [
                        "SoC Design Engineer",
                        "ASIC Design Engineer",
                        "SoC Integration Engineer",
                        "SoC Engineer",
                        "VLSI Design Engineer",
                    ],
                    "chips":   ["mobile", "automotive", "datacenter", "IoT", "5G", "AI accelerator"],
                    "tools":   ["SystemVerilog", "Synopsys", "Cadence", "Xilinx", "Design Compiler"],
                    "concepts":["SoC", "ASIC", "IP integration", "power domains", "clock domain crossing",
                                "physical design", "tapeout", "DFT"],
                },
                "must_have_any": [
                    "SoC", "ASIC", "system on chip", "VLSI", "tapeout", "IP integration",
                    "physical design", "chip design", "RTL", "SystemVerilog", "Verilog",
                ],
                "scoring_context": """
Candidate: Praveen Saravanan — SoC / ASIC Design Engineer
Core strengths:
- GPU RTL @ Samsung: full flow spec→RTL→PD handoff for next-gen mobile GPU (tapeout-bound)
- FPGA security research @ UF: multi-tenant cloud FPGA RTL, IP integration
- RTL synthesis pipelines @ Phinity Labs: Yosys, OpenSTA, cocotb
- Skills: SystemVerilog, Verilog, Synopsys VCS/DC/Verdi, Xilinx Vivado, PCIe, AMBA AXI
Target: SoC design, ASIC design, IP integration, mobile/automotive/datacenter chip roles.
""",
            },
        },
    },
}


# ---------------------------------------------------------------------------
# COMPANIES — curated target companies per track
# ---------------------------------------------------------------------------

COMPANIES = {
    "HW": {
        "tier1": [
            "NVIDIA", "AMD", "Qualcomm", "Apple", "Intel", "Broadcom",
            "Marvell", "Arm", "Samsung", "MediaTek", "Texas Instruments",
        ],
        "tier2": [
            "Tenstorrent", "SiFive", "Rivos", "Ampere", "d-Matrix",
            "Groq", "Cerebras", "Ventana", "Esperanto", "Untether AI",
        ],
        "crossover": [
            "Google", "Meta", "Amazon", "Microsoft", "Tesla",
        ],
    },
    "AI": {
        "tier1": [
            "OpenAI", "Anthropic", "Google", "Meta", "xAI", "Mistral",
        ],
        "tier2": [
            "Scale AI", "Cohere", "Together AI", "Modal", "Hugging Face",
            "Databricks", "Weights & Biases", "Replicate", "Baseten", "Runway",
        ],
    },
}


# ---------------------------------------------------------------------------
# Global search settings
# ---------------------------------------------------------------------------

MIN_SCORE = 6           # notify if LLM score >= this
TIER1_BONUS = 1         # score bonus added for Tier 1 company matches
CHECK_INTERVAL_HOURS = 3
MAX_JOBS_PER_QUERY = 10
