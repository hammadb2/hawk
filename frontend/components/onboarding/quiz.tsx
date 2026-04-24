"use client";

import { useState } from "react";

interface Props {
  module: string;
  onComplete: (module: string, score: number, passed: boolean) => void;
}

/* Placeholder quiz data — user will fill in real content before go-live */
const QUIZ_DATA: Record<string, { question: string; options: string[]; correct: number }[]> = {
  hawk_security: [
    {
      question: "What does Hawk Security specialize in?",
      options: [
        "Social media management",
        "Automated attack surface scanning and risk mitigation",
        "Accounting software",
        "HR management",
      ],
      correct: 1,
    },
    {
      question: "What is the Hawk Score?",
      options: [
        "A credit score for businesses",
        "A 0-100 rating of a domain's security posture",
        "A customer satisfaction metric",
        "An employee performance rating",
      ],
      correct: 1,
    },
    {
      question: "What type of businesses does Hawk Security primarily serve?",
      options: [
        "Only Fortune 500 companies",
        "Consumer retail brands",
        "Small to mid-size businesses concerned about cybersecurity",
        "Government agencies exclusively",
      ],
      correct: 2,
    },
  ],
  target_verticals: [
    {
      question: "What are the three target verticals for Hawk Security?",
      options: [
        "Retail, hospitality, entertainment",
        "Dental, legal, accounting",
        "Healthcare, finance, education",
        "Tech, manufacturing, logistics",
      ],
      correct: 1,
    },
    {
      question: "Why are these verticals targeted?",
      options: [
        "They have the largest companies",
        "They handle sensitive client data and face compliance requirements",
        "They spend the most on marketing",
        "They have the most employees",
      ],
      correct: 1,
    },
  ],
  products: [
    {
      question: "What is the monthly price for the Starter plan?",
      options: ["$99/mo", "$199/mo", "$499/mo", "$997/mo"],
      correct: 1,
    },
    {
      question: "What is the monthly price for the Shield plan?",
      options: ["$199/mo", "$499/mo", "$997/mo", "$2,500/mo"],
      correct: 2,
    },
    {
      question: "What is the monthly price for the Enterprise plan?",
      options: ["$997/mo", "$1,500/mo", "$2,500/mo", "$5,000/mo"],
      correct: 2,
    },
  ],
  hawk_certified: [
    {
      question: "How long does it take to earn the HAWK Certified badge?",
      options: ["30 days", "60 days", "90 days", "120 days"],
      correct: 2,
    },
    {
      question: "What does the HAWK Certified badge indicate?",
      options: [
        "The company has paid for the premium plan",
        "The company has maintained high security standards consistently",
        "The company has completed a training course",
        "The company has referred other businesses",
      ],
      correct: 1,
    },
  ],
  financial_guarantee: [
    {
      question: "What is the Breach Response Guarantee?",
      options: [
        "A money-back guarantee on subscriptions",
        "A contractual warranty for compliant Shield users",
        "An insurance policy sold separately",
        "A free trial offer",
      ],
      correct: 1,
    },
    {
      question: "Who is eligible for the financial guarantee?",
      options: [
        "All customers",
        "Only Enterprise customers",
        "Compliant Shield users who maintain their Readiness Score",
        "Only customers who have been with Hawk for over a year",
      ],
      correct: 2,
    },
  ],
};

const PASSING_SCORE = 70;

export function OnboardingQuiz({ module, onComplete }: Props) {
  const questions = QUIZ_DATA[module] || QUIZ_DATA.hawk_security;
  const [currentQ, setCurrentQ] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [answers, setAnswers] = useState<number[]>([]);
  const [showResult, setShowResult] = useState(false);

  function selectAnswer(idx: number) {
    if (selected !== null) return;
    setSelected(idx);
  }

  function nextQuestion() {
    if (selected === null) return;
    const newAnswers = [...answers, selected];
    setAnswers(newAnswers);
    setSelected(null);

    if (currentQ + 1 >= questions.length) {
      const correct = newAnswers.filter((a, i) => a === questions[i].correct).length;
      const score = Math.round((correct / questions.length) * 100);
      setShowResult(true);
      setTimeout(() => onComplete(module, score, score >= PASSING_SCORE), 2000);
    } else {
      setCurrentQ(currentQ + 1);
    }
  }

  if (showResult) {
    const correct = answers.filter((a, i) => a === questions[i].correct).length;
    const score = Math.round((correct / questions.length) * 100);
    const passed = score >= PASSING_SCORE;
    return (
      <div className="rounded-lg border border-ink-700 bg-[#161625] p-6 text-center">
        <p className={`text-2xl font-bold ${passed ? "text-signal" : "text-red"}`}>{score}%</p>
        <p className="mt-2 text-sm text-ink-200">
          {passed ? "You passed! Moving on..." : "You need 70% to pass. The AI will help you retry."}
        </p>
      </div>
    );
  }

  const q = questions[currentQ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-ink-0">
          Question {currentQ + 1} of {questions.length}
        </p>
        <p className="text-xs text-ink-0">{module.replace(/_/g, " ")}</p>
      </div>
      <p className="text-sm font-medium text-white">{q.question}</p>
      <div className="space-y-2">
        {q.options.map((opt, i) => (
          <button
            key={i}
            onClick={() => selectAnswer(i)}
            className={`w-full rounded-lg border px-4 py-3 text-left text-sm transition ${
              selected === null
                ? "border-ink-700 bg-[#161625] text-ink-100 hover:border-signal/50"
                : i === q.correct
                  ? "border-signal bg-signal/10 text-signal"
                  : i === selected
                    ? "border-red bg-red/100/10 text-red"
                    : "border-ink-700 bg-[#161625] text-ink-0"
            }`}
          >
            {opt}
          </button>
        ))}
      </div>
      {selected !== null && (
        <button
          onClick={nextQuestion}
          className="rounded-lg bg-signal-400 px-5 py-2 text-sm font-semibold text-white hover:bg-signal-600 transition"
        >
          {currentQ + 1 >= questions.length ? "See Results" : "Next Question"}
        </button>
      )}
    </div>
  );
}
