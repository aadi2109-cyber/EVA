import React, { useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle2, LoaderCircle, MessageSquareText, ShieldCheck } from 'lucide-react';
import { User } from '../api/types';
import { api } from '../api/client';

interface LoginProps {
  onLoginSuccess: (user: User, token: string) => void;
  message?: string;
}

export const Login: React.FC<LoginProps> = ({ onLoginSuccess, message }) => {
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'phone' | 'code'>('phone');
  const [otpId, setOtpId] = useState<string | null>(null);
  const [email, setEmail] = useState<string>('user@eva.local');
  const [password, setPassword] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showPasswordLogin, setShowPasswordLogin] = useState(false);
  const [resendAvailableAt, setResendAvailableAt] = useState(0);
  const [resendWaitSeconds, setResendWaitSeconds] = useState(0);
  const [deliveryNotice, setDeliveryNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!resendAvailableAt) return;
    const update = () => setResendWaitSeconds(Math.max(0, Math.ceil((resendAvailableAt - Date.now()) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [resendAvailableAt]);

  useEffect(() => {
    if (!otpId) return;
    let active = true;
    let attempts = 0;
    const checkStatus = async () => {
      try {
        const result = await api.auth.getOtpStatus(otpId);
        if (!active) return;
        if (result.status === 'delivered') {
          setDeliveryNotice(`Code delivered${result.channel ? ` via ${result.channel === 'sms' ? 'SMS' : 'WhatsApp'}` : ''}. Check your messages.`);
          return true;
        }
        if (result.status === 'failed') {
          setDeliveryNotice('MiniMoth could not deliver this code. Check Dashboard → Usage → Failed deliveries for the request reason, then retry later.');
          return true;
        }
        setDeliveryNotice('Your code is queued for delivery. Check WhatsApp and SMS shortly.');
      } catch {
        if (active) setDeliveryNotice('Delivery status is temporarily unavailable. You can still enter a code if it arrives.');
        return true;
      }
      return false;
    };

    let timer: number | undefined;
    const poll = async () => {
      const finished = await checkStatus();
      attempts += 1;
      if (active && !finished && attempts < 5) timer = window.setTimeout(poll, 2500);
      else if (active && !finished) setDeliveryNotice('Delivery is taking longer than usual. Check WhatsApp and SMS, or resend when available.');
    };
    void poll();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [otpId]);

  const doLogin = async (em: string, pw: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const { user, access_token } = await api.auth.login(em, pw);
      onLoginSuccess(user, access_token);
    } catch (err: any) {
      setError(err?.message || 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void doLogin(email, password);
  };

  const sendCode = async () => {
    if (resendAvailableAt && Date.now() < resendAvailableAt) return;
    const normalized = phone.trim();
    if (!/^[6-9]\d{9}$/.test(normalized)) {
      setError('Enter a valid 10-digit Indian mobile number starting with 6–9.');
      setNotice(null);
      return;
    }
    setIsLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.auth.sendOtp(`+91${normalized}`);
      setOtpId(result.otp_id ?? null);
      setStep('code');
      setResendAvailableAt(Date.now() + 60_000);
      setDeliveryNotice('OTP request accepted. Checking delivery status…');
      setNotice(null);
    } catch (err: any) {
      setError(err?.message || 'We could not send a code just now. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const verifyCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!/^\d{6}$/.test(code)) {
      setError('Enter the 6-digit code from your message.');
      return;
    }
    setIsLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.auth.verifyOtp(`+91${phone}`, code);
      onLoginSuccess(result.user, result.access_token);
    } catch (err: any) {
      const message = String(err?.message || 'We could not verify that code.');
      setError(/invalid|expired|verification code/i.test(message)
        ? 'That code is invalid or has expired. Check it and try again, or request a new code.'
        : message);
    } finally {
      setIsLoading(false);
    }
  };

  const editPhone = () => {
    setStep('phone');
    setCode('');
    setOtpId(null);
    setDeliveryNotice(null);
    setError(null);
    setNotice(null);
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-background relative overflow-hidden">
      {/* Background Glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-96 h-96 bg-primary-container/10 rounded-full blur-[140px] pointer-events-none" />

      <div className="w-full max-w-md bg-surface-container-low/90 backdrop-blur-2xl border border-white/10 rounded-3xl p-6 sm:p-8 shadow-[0_25px_80px_rgba(0,0,0,0.8)] relative z-10 space-y-6">
        {/* Brand */}
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-2xl bg-primary-container/15 border border-primary-container/40 text-primary-container flex items-center justify-center mx-auto shadow-[0_0_20px_rgba(200,243,34,0.3)]">
            <span className="material-symbols-outlined text-[28px]">
              verified_user
            </span>
          </div>
          <h2 className="text-xl font-bold text-white tracking-tight">
            EVA AI Enclave Access
          </h2>
          <p className="text-xs text-on-surface-variant">Secure access to your AI agent workspace</p>
        </div>

        {message && <div role="status" className="text-[11px] leading-relaxed text-amber-200 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">{message}</div>}

        {!showPasswordLogin && (
          <>
            <div className="flex items-center gap-2" aria-label={`Step ${step === 'phone' ? 1 : 2} of 2`}>
              <span className={`h-1.5 flex-1 rounded-full ${step === 'phone' ? 'bg-primary-container' : 'bg-primary-container/50'}`} />
              <span className={`h-1.5 flex-1 rounded-full ${step === 'code' ? 'bg-primary-container' : 'bg-white/10'}`} />
            </div>

            {step === 'phone' ? (
              <form onSubmit={(e) => { e.preventDefault(); void sendCode(); }} className="space-y-4 text-xs">
                <div className="space-y-2">
                  <label htmlFor="phone" className="font-bold text-white uppercase tracking-wider text-[11px] block">Phone number</label>
                  <div className="flex gap-2">
                    <div aria-label="Country code" className="flex items-center gap-2 px-3 rounded-xl bg-surface-container-lowest border border-white/10 text-white font-mono">
                      <span aria-hidden="true">🇮🇳</span><span>+91</span>
                    </div>
                    <input
                      id="phone"
                      type="tel"
                      inputMode="numeric"
                      autoComplete="tel-national"
                      aria-describedby="phone-help"
                      aria-invalid={Boolean(error)}
                      required
                      maxLength={10}
                      value={phone}
                      onChange={(e) => { setPhone(e.target.value.replace(/\D/g, '').slice(0, 10)); setError(null); setNotice(null); }}
                      placeholder="98765 43210"
                      className="min-w-0 flex-1 px-3.5 py-3 rounded-xl bg-surface-container-lowest border border-white/10 text-white font-mono tracking-wider placeholder:text-on-surface-variant/50 focus:outline-none focus:ring-1 focus:ring-primary-container"
                    />
                  </div>
                  <p id="phone-help" className="text-[11px] leading-relaxed text-on-surface-variant">We’ll send a one-time verification code to your Indian mobile number.</p>
                </div>
                {error && <div role="alert" className="text-[11px] text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg px-3 py-2">{error}</div>}
                <button type="submit" disabled={isLoading || phone.length !== 10} className="w-full py-3 rounded-xl bg-primary-container text-on-primary-container font-bold text-xs shadow-[0_0_20px_rgba(200,243,34,0.25)] hover:brightness-105 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2">
                  {isLoading ? <LoaderCircle size={16} className="animate-spin" /> : <MessageSquareText size={16} />}
                  <span>{isLoading ? 'Sending code…' : 'Send verification code'}</span>
                </button>
              </form>
            ) : (
              <form onSubmit={(e) => void verifyCode(e)} className="space-y-4 text-xs">
                <button type="button" onClick={editPhone} className="inline-flex items-center gap-1.5 text-on-surface-variant hover:text-white transition-colors"><ArrowLeft size={14} /> Edit phone number</button>
                <div className="rounded-xl border border-primary-container/20 bg-primary-container/5 px-3.5 py-3">
                  <p className="text-[11px] text-on-surface-variant">Code sent to</p>
                  <p className="mt-0.5 text-sm font-semibold font-mono text-white">+91 {phone}</p>
                </div>
                {(notice || deliveryNotice) && <div role="status" className="flex gap-2 text-[11px] leading-relaxed text-emerald-200"><CheckCircle2 size={15} className="shrink-0 mt-0.5" />{notice || deliveryNotice}</div>}
                <div className="space-y-2">
                  <label htmlFor="otp-code" className="font-bold text-white uppercase tracking-wider text-[11px] block">6-digit verification code</label>
                  <input
                    id="otp-code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    required
                    autoFocus
                    value={code}
                    onChange={(e) => { setCode(e.target.value.replace(/\D/g, '').slice(0, 6)); setError(null); }}
                    aria-invalid={Boolean(error)}
                    aria-describedby="otp-help"
                    placeholder="••••••"
                    className="w-full px-3.5 py-3.5 rounded-xl bg-surface-container-lowest border border-white/10 text-white text-center text-2xl font-mono tracking-[0.45em] placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-primary-container"
                  />
                  <p id="otp-help" className="text-[11px] text-on-surface-variant">The code expires after a short time. Enter it as a six-digit code.</p>
                </div>
                {error && <div role="alert" className="text-[11px] leading-relaxed text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg px-3 py-2">{error}</div>}
                <button type="submit" disabled={isLoading || code.length !== 6} className="w-full py-3 rounded-xl bg-primary-container text-on-primary-container font-bold text-xs shadow-[0_0_20px_rgba(200,243,34,0.25)] hover:brightness-105 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2">
                  {isLoading ? <LoaderCircle size={16} className="animate-spin" /> : <ShieldCheck size={16} />}
                  <span>{isLoading ? 'Verifying…' : 'Verify and continue'}</span>
                  {!isLoading && <ArrowRight size={15} />}
                </button>
                <button type="button" aria-label="Resend code" onClick={() => void sendCode()} disabled={isLoading || resendWaitSeconds > 0} className="w-full py-2 text-on-surface-variant hover:text-white disabled:opacity-50 transition-colors">{isLoading ? 'Please wait…' : resendWaitSeconds > 0 ? `Available in ${resendWaitSeconds}s` : 'Resend code'}</button>
                <span className="sr-only">Request reference: {otpId ?? 'not provided'}</span>
              </form>
            )}
            <div className="border-t border-white/10 pt-4 text-center">
              <button type="button" onClick={() => { setShowPasswordLogin(true); setError(null); setNotice(null); }} className="text-[11px] text-on-surface-variant hover:text-white underline underline-offset-4">Use email and password instead</button>
            </div>
          </>
        )}

        {showPasswordLogin && (
          <form onSubmit={handleSubmit} className="space-y-4 text-xs">
            <button type="button" onClick={() => { setShowPasswordLogin(false); setError(null); }} className="inline-flex items-center gap-1.5 text-on-surface-variant hover:text-white"><ArrowLeft size={14} /> Use phone verification</button>
            <div className="space-y-1">
              <label htmlFor="email" className="font-bold text-white uppercase tracking-wider text-[11px] block">Email</label>
              <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-full px-3.5 py-2.5 rounded-xl bg-surface-container-lowest border border-white/10 text-white font-mono focus:outline-none focus:ring-1 focus:ring-primary-container" />
            </div>
            <div className="space-y-1">
              <label htmlFor="password" className="font-bold text-white uppercase tracking-wider text-[11px] block">Password</label>
              <input id="password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="w-full px-3.5 py-2.5 rounded-xl bg-surface-container-lowest border border-white/10 text-white font-mono focus:outline-none focus:ring-1 focus:ring-primary-container" />
            </div>
            {error && <div role="alert" className="text-[11px] text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg px-3 py-2">{error}</div>}
            <button type="submit" disabled={isLoading} className="w-full py-3 rounded-xl bg-primary-container text-on-primary-container font-bold text-xs shadow-[0_0_20px_rgba(200,243,34,0.35)] disabled:opacity-50 flex items-center justify-center gap-2">
              {isLoading ? <LoaderCircle size={16} className="animate-spin" /> : <ShieldCheck size={16} />}
              <span>{isLoading ? 'Signing in…' : 'Authenticate session'}</span>
            </button>
          </form>
        )}

        <div className="flex items-center justify-center gap-1.5 text-[10px] text-on-surface-variant/80"><ShieldCheck size={13} /> Your phone is verified securely by EVA’s backend</div>

      </div>
    </div>
  );
};
