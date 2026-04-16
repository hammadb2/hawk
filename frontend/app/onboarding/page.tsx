"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import { OnboardingSignaturePad } from "@/components/onboarding/signature-pad";
import { OnboardingQuiz } from "@/components/onboarding/quiz";
import { OnboardingFileUpload } from "@/components/onboarding/file-upload";

/* ── Types ────────────────────────────────────────────────────────────── */

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

/* ── Constants ────────────────────────────────────────────────────────── */

const STEPS = [
  { num: 1, label: "Welcome" },
  { num: 2, label: "Personal Details" },
  { num: 3, label: "Government ID" },
  { num: 4, label: "Bank Details" },
  { num: 5, label: "Documents & Signing" },
  { num: 6, label: "Product Training" },
  { num: 7, label: "Submit" },
];

/* ── Main Component ───────────────────────────────────────────────────── */

export default function OnboardingPage() {
  const supabase = useMemo(() => createClient(), []);
  const [userId, setUserId] = useState<string | null>(null);
  const [userName, setUserName] = useState("");
  const [loading, setLoading] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [currentStep, setCurrentStep] = useState(1);
  const [showSignature, setShowSignature] = useState(false);
  const [signingDocType, setSigningDocType] = useState<string>("");
  const [signedDocs, setSignedDocs] = useState<Set<string>>(new Set());
  const [showQuiz, setShowQuiz] = useState(false);
  const [quizModule, setQuizModule] = useState("");
  const [completedModules, setCompletedModules] = useState<Set<string>>(new Set());
  const [showUpload, setShowUpload] = useState(false);
  const [personalDetails, setPersonalDetails] = useState<Record<string, string>>({});
  const [bankDetails, setBankDetails] = useState<Record<string, string>>({});
  const chatEndRef = useRef<HTMLDivElement>(null);

  const token = useCallback(async () => {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token || "";
  }, [supabase]);

  const authHeaders = useCallback(async () => {
    const t = await token();
    return { Authorization: `Bearer ${t}`, "Content-Type": "application/json" };
  }, [token]);

  /* ── Init ────────────────────────────────────────────────────────────── */

  useEffect(() => {
    void (async () => {
      const { data: authData } = await supabase.auth.getUser();
      if (!authData.user) {
        window.location.href = "/crm/login?next=/onboarding";
        return;
      }
      setUserId(authData.user.id);

      const { data: prof } = await supabase
        .from("profiles")
        .select("full_name,role,role_type,onboarding_status")
        .eq("id", authData.user.id)
        .maybeSingle();

      if (prof?.onboarding_status === "approved") {
        window.location.href = "/crm/dashboard";
        return;
      }
      if (prof?.role === "ceo") {
        window.location.href = "/crm/dashboard";
        return;
      }

      setUserName(prof?.full_name || "");

      try {
        const headers = await authHeaders();
        const r = await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/session`, { headers });
        if (r.ok) {
          const sess = await r.json();
          setCurrentStep(sess.current_step || 1);
        }
      } catch (err) {
        console.error("Failed to load onboarding session:", err);
      }

      setLoading(false);
    })();
  }, [supabase, authHeaders]);

  /* Auto-send welcome on step 1 */
  useEffect(() => {
    if (!loading && currentStep === 1 && messages.length === 0 && userName) {
      void sendToAI("Hello, I'm ready to start onboarding.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, currentStep, userName]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /* ── AI Chat ────────────────────────────────────────────────────────── */

  async function sendToAI(userMessage: string) {
    if (!userMessage.trim()) return;
    setSending(true);

    const userMsg: ChatMessage = { role: "user", content: userMessage };
    const updated = [...messages, userMsg];
    setMessages(updated);

    try {
      const headers = await authHeaders();
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          messages: updated.map((m) => ({ role: m.role, content: m.content })),
          step: currentStep,
          context: {
            personalDetails,
            bankDetails,
            signedDocs: Array.from(signedDocs),
            completedModules: Array.from(completedModules),
          },
        }),
      });

      if (r.ok) {
        const data = await r.json();
        setMessages([...updated, { role: "assistant", content: data.reply }]);
      } else {
        setMessages([
          ...updated,
          { role: "assistant", content: "I'm having trouble connecting. Please try again in a moment." },
        ]);
      }
    } catch {
      setMessages([
        ...updated,
        { role: "assistant", content: "Connection error. Please check your internet and try again." },
      ]);
    }
    setSending(false);
  }

  function handleSend() {
    if (!input.trim() || sending) return;
    const msg = input;
    setInput("");
    void sendToAI(msg);
  }

  /* ── Step progression ───────────────────────────────────────────────── */

  async function advanceStep(nextStep: number) {
    setCurrentStep(nextStep);
    try {
      const headers = await authHeaders();
      await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/session/step`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ current_step: nextStep }),
      });
    } catch {
      // silent
    }
    void sendToAI(`I've completed step ${nextStep - 1} and I'm ready for step ${nextStep}.`);
  }

  /* ── Personal details ───────────────────────────────────────────────── */

  async function savePersonalDetails() {
    try {
      const headers = await authHeaders();
      await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/personal-details`, {
        method: "POST",
        headers,
        body: JSON.stringify(personalDetails),
      });
      void advanceStep(3);
    } catch {
      void sendToAI("There was an error saving my personal details. Can you help?");
    }
  }

  /* ── Bank details ───────────────────────────────────────────────────── */

  async function saveBankDetails() {
    try {
      const headers = await authHeaders();
      await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/bank-details`, {
        method: "POST",
        headers,
        body: JSON.stringify(bankDetails),
      });
      void advanceStep(5);
    } catch {
      void sendToAI("There was an error saving my bank details. Can you help?");
    }
  }

  /* ── Government ID upload ───────────────────────────────────────────── */

  async function handleGovIdUpload(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    try {
      const t = await token();
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/upload-gov-id`, {
        method: "POST",
        headers: { Authorization: `Bearer ${t}` },
        body: formData,
      });
      if (r.ok) {
        setShowUpload(false);
        void advanceStep(4);
      }
    } catch {
      void sendToAI("There was an error uploading my ID. Can you help?");
    }
  }

  /* ── Document signing ───────────────────────────────────────────────── */

  async function handleSignature(signatureData: string) {
    try {
      const headers = await authHeaders();
      await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/sign-document`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          document_type: signingDocType,
          signature_data: signatureData,
        }),
      });
      const newSigned = new Set(signedDocs);
      newSigned.add(signingDocType);
      setSignedDocs(newSigned);
      setShowSignature(false);

      if (newSigned.size >= 3) {
        void advanceStep(6);
      } else {
        const docs = ["contract", "nda", "acceptable_use"];
        const next = docs.find((d) => !newSigned.has(d));
        if (next) {
          setSigningDocType(next);
          void sendToAI(`I've signed the ${signingDocType}. What's next?`);
        }
      }
    } catch {
      void sendToAI("There was an error recording my signature. Can you help?");
    }
  }

  /* ── Quiz ────────────────────────────────────────────────────────────── */

  async function handleQuizComplete(module: string, score: number, passed: boolean) {
    try {
      const headers = await authHeaders();
      await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/quiz-result`, {
        method: "POST",
        headers,
        body: JSON.stringify({ module, score, passed }),
      });
      if (passed) {
        const newMods = new Set(completedModules);
        newMods.add(module);
        setCompletedModules(newMods);
      }
      setShowQuiz(false);
      void sendToAI(
        passed
          ? `I passed the ${module} quiz with a score of ${score}%. What's next?`
          : `I scored ${score}% on the ${module} quiz but didn't pass. Can I retry?`
      );
    } catch {
      setShowQuiz(false);
    }
  }

  /* ── Submit ──────────────────────────────────────────────────────────── */

  async function submitOnboarding() {
    try {
      const headers = await authHeaders();
      await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/submit`, {
        method: "POST",
        headers,
      });
      window.location.href = "/onboarding/complete";
    } catch {
      void sendToAI("There was an error submitting. Can you help?");
    }
  }

  /* ── Render ──────────────────────────────────────────────────────────── */

  if (loading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-[#0a0a12]">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-700 border-t-emerald-500" />
          <p className="text-sm text-slate-400">Loading onboarding...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh bg-[#0a0a12]">
      {/* Sidebar — step progress */}
      <aside className="hidden w-72 flex-shrink-0 border-r border-slate-800 bg-[#0d0d18] p-6 lg:block">
        <div className="mb-8">
          <h2 className="text-lg font-bold text-white">HAWK</h2>
          <p className="text-xs text-slate-500">Onboarding Portal</p>
        </div>
        <nav className="space-y-1">
          {STEPS.map((s) => (
            <div
              key={s.num}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                s.num === currentStep
                  ? "bg-emerald-500/10 text-emerald-400 font-medium"
                  : s.num < currentStep
                    ? "text-slate-400"
                    : "text-slate-600"
              }`}
            >
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                  s.num < currentStep
                    ? "bg-emerald-500 text-white"
                    : s.num === currentStep
                      ? "bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/40"
                      : "bg-slate-800 text-slate-600"
                }`}
              >
                {s.num < currentStep ? "\u2713" : s.num}
              </span>
              {s.label}
            </div>
          ))}
        </nav>
      </aside>

      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {/* Mobile step indicator */}
        <div className="flex items-center justify-between border-b border-slate-800 bg-[#0d0d18] px-4 py-3 lg:hidden">
          <span className="text-sm font-bold text-white">HAWK Onboarding</span>
          <span className="text-xs text-slate-400">
            Step {currentStep} of {STEPS.length}
          </span>
        </div>

        {/* Chat messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6 lg:px-8">
          <div className="mx-auto max-w-2xl space-y-4">
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-emerald-600 text-white"
                      : "bg-[#161625] text-slate-300 border border-slate-800"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <p className="mb-1 text-xs font-semibold text-emerald-400">HAWK Guide</p>
                  )}
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-[#161625] border border-slate-800 px-4 py-3">
                  <p className="text-xs font-semibold text-emerald-400 mb-1">HAWK Guide</p>
                  <div className="flex gap-1">
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-500" style={{ animationDelay: "0ms" }} />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-500" style={{ animationDelay: "150ms" }} />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-500" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        </div>

        {/* Step-specific action panels */}
        {currentStep === 2 && (
          <PersonalDetailsForm
            details={personalDetails}
            onChange={setPersonalDetails}
            onSubmit={savePersonalDetails}
          />
        )}
        {currentStep === 3 && showUpload && (
          <div className="border-t border-slate-800 bg-[#0d0d18] p-4">
            <div className="mx-auto max-w-2xl">
              <OnboardingFileUpload onUpload={handleGovIdUpload} />
            </div>
          </div>
        )}
        {currentStep === 4 && (
          <BankDetailsForm details={bankDetails} onChange={setBankDetails} onSubmit={saveBankDetails} />
        )}
        {currentStep === 5 && showSignature && (
          <div className="border-t border-slate-800 bg-[#0d0d18] p-4">
            <div className="mx-auto max-w-2xl">
              <p className="mb-3 text-sm text-slate-400">
                Sign the <span className="font-semibold text-white">{signingDocType.replace("_", " ")}</span>:
              </p>
              <OnboardingSignaturePad onSign={handleSignature} onCancel={() => setShowSignature(false)} />
            </div>
          </div>
        )}
        {currentStep === 6 && showQuiz && (
          <div className="border-t border-slate-800 bg-[#0d0d18] p-4">
            <div className="mx-auto max-w-2xl">
              <OnboardingQuiz module={quizModule} onComplete={handleQuizComplete} />
            </div>
          </div>
        )}
        {currentStep === 7 && (
          <div className="border-t border-slate-800 bg-[#0d0d18] p-4">
            <div className="mx-auto max-w-2xl text-center">
              <button
                onClick={submitOnboarding}
                className="rounded-lg bg-emerald-600 px-8 py-3 text-sm font-semibold text-white hover:bg-emerald-700 transition"
              >
                Submit Onboarding for Review
              </button>
            </div>
          </div>
        )}

        {/* Quick action buttons */}
        {currentStep === 3 && !showUpload && (
          <div className="border-t border-slate-800 bg-[#0d0d18] px-4 py-3">
            <div className="mx-auto max-w-2xl">
              <button
                onClick={() => setShowUpload(true)}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition"
              >
                Upload Government ID
              </button>
            </div>
          </div>
        )}
        {currentStep === 5 && !showSignature && (
          <div className="border-t border-slate-800 bg-[#0d0d18] px-4 py-3">
            <div className="mx-auto flex max-w-2xl gap-2">
              {["contract", "nda", "acceptable_use"].map((doc) => (
                <button
                  key={doc}
                  disabled={signedDocs.has(doc)}
                  onClick={() => {
                    setSigningDocType(doc);
                    setShowSignature(true);
                  }}
                  className={`rounded-lg px-3 py-2 text-xs font-medium transition ${
                    signedDocs.has(doc)
                      ? "bg-emerald-900/30 text-emerald-400 cursor-default"
                      : "bg-blue-600 text-white hover:bg-blue-700"
                  }`}
                >
                  {signedDocs.has(doc) ? "\u2713 " : ""}
                  Sign {doc.replace("_", " ")}
                </button>
              ))}
            </div>
          </div>
        )}
        {currentStep === 6 && !showQuiz && (
          <div className="border-t border-slate-800 bg-[#0d0d18] px-4 py-3">
            <div className="mx-auto flex max-w-2xl flex-wrap gap-2">
              {["hawk_security", "target_verticals", "products", "hawk_certified", "financial_guarantee"].map(
                (mod) => (
                  <button
                    key={mod}
                    disabled={completedModules.has(mod)}
                    onClick={() => {
                      setQuizModule(mod);
                      setShowQuiz(true);
                    }}
                    className={`rounded-lg px-3 py-2 text-xs font-medium transition ${
                      completedModules.has(mod)
                        ? "bg-emerald-900/30 text-emerald-400 cursor-default"
                        : "bg-blue-600 text-white hover:bg-blue-700"
                    }`}
                  >
                    {completedModules.has(mod) ? "\u2713 " : ""}
                    {mod.replace(/_/g, " ")}
                  </button>
                )
              )}
            </div>
          </div>
        )}

        {/* Chat input */}
        <div className="border-t border-slate-800 bg-[#0a0a12] px-4 py-4">
          <div className="mx-auto flex max-w-2xl gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Type a message..."
              className="flex-1 rounded-xl border border-slate-700 bg-[#161625] px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500/20"
            />
            <button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className="rounded-xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50 transition"
            >
              Send
            </button>
            {currentStep < 7 && currentStep > 1 && (
              <button
                onClick={() => void advanceStep(currentStep + 1)}
                className="rounded-xl bg-slate-700 px-4 py-3 text-sm font-medium text-slate-300 hover:bg-slate-600 transition"
              >
                Next Step
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Personal Details Form ────────────────────────────────────────────── */

function PersonalDetailsForm({
  details,
  onChange,
  onSubmit,
}: {
  details: Record<string, string>;
  onChange: (d: Record<string, string>) => void;
  onSubmit: () => void;
}) {
  const fields = [
    { key: "phone", label: "Phone Number", placeholder: "+1 555 123 4567" },
    { key: "whatsapp", label: "WhatsApp Number", placeholder: "+1 555 123 4567" },
    { key: "address", label: "Full Address", placeholder: "123 Main St, City, State" },
    { key: "country", label: "Country", placeholder: "Canada" },
    { key: "date_of_birth", label: "Date of Birth", placeholder: "YYYY-MM-DD", type: "date" },
    { key: "emergency_contact_name", label: "Emergency Contact Name", placeholder: "Jane Doe" },
    { key: "emergency_contact_phone", label: "Emergency Contact Phone", placeholder: "+1 555 987 6543" },
  ];

  return (
    <div className="border-t border-slate-800 bg-[#0d0d18] p-4">
      <div className="mx-auto max-w-2xl">
        <p className="mb-3 text-sm font-semibold text-white">Personal Details</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {fields.map((f) => (
            <div key={f.key}>
              <label className="mb-1 block text-xs text-slate-400">{f.label}</label>
              <input
                type={f.type || "text"}
                placeholder={f.placeholder}
                value={details[f.key] || ""}
                onChange={(e) => onChange({ ...details, [f.key]: e.target.value })}
                className="w-full rounded-lg border border-slate-700 bg-[#161625] px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-emerald-500 focus:outline-none"
              />
            </div>
          ))}
        </div>
        <button
          onClick={onSubmit}
          className="mt-4 rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 transition"
        >
          Save &amp; Continue
        </button>
      </div>
    </div>
  );
}

/* ── Bank Details Form ────────────────────────────────────────────────── */

function BankDetailsForm({
  details,
  onChange,
  onSubmit,
}: {
  details: Record<string, string>;
  onChange: (d: Record<string, string>) => void;
  onSubmit: () => void;
}) {
  const fields = [
    { key: "full_name", label: "Full Name on Account", placeholder: "John Doe" },
    { key: "bank_name", label: "Bank Name", placeholder: "TD Bank" },
    { key: "account_number", label: "Account Number", placeholder: "****1234" },
    { key: "routing_or_swift", label: "Routing / SWIFT Code", placeholder: "TDOMCATTTOR" },
    { key: "payment_method", label: "Payment Method", placeholder: "Direct Deposit / Wire / PayPal" },
    { key: "notes", label: "Notes (optional)", placeholder: "Any special instructions" },
  ];

  return (
    <div className="border-t border-slate-800 bg-[#0d0d18] p-4">
      <div className="mx-auto max-w-2xl">
        <p className="mb-3 text-sm font-semibold text-white">Bank Details</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {fields.map((f) => (
            <div key={f.key}>
              <label className="mb-1 block text-xs text-slate-400">{f.label}</label>
              <input
                type="text"
                placeholder={f.placeholder}
                value={details[f.key] || ""}
                onChange={(e) => onChange({ ...details, [f.key]: e.target.value })}
                className="w-full rounded-lg border border-slate-700 bg-[#161625] px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-emerald-500 focus:outline-none"
              />
            </div>
          ))}
        </div>
        <button
          onClick={onSubmit}
          className="mt-4 rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 transition"
        >
          Save &amp; Continue
        </button>
      </div>
    </div>
  );
}
