import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Login } from '../src/pages/Login';

const { sendOtp, getOtpStatus, verifyOtp, login } = vi.hoisted(() => ({
  sendOtp: vi.fn(),
  getOtpStatus: vi.fn(),
  verifyOtp: vi.fn(),
  login: vi.fn(),
}));

vi.mock('../src/api/client', () => ({
  api: { auth: { sendOtp, getOtpStatus, verifyOtp, login } },
}));

const user = { id: 'u1', email: null, phone: '+919876543210', role: 'user' as const, name: '+919876543210' };

describe('phone OTP login', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('validates an Indian mobile number before sending', async () => {
    const onLoginSuccess = vi.fn();
    render(<Login onLoginSuccess={onLoginSuccess} />);
    await userEvent.type(screen.getByLabelText('Phone number'), '5123456789');
    await userEvent.click(screen.getByRole('button', { name: 'Send verification code' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/starting with 6–9/);
    expect(sendOtp).not.toHaveBeenCalled();
  });

  it('sends a code, verifies it as a string, then returns the authenticated EVA user', async () => {
    sendOtp.mockResolvedValue({ message: 'sent', otp_id: 'otp-1' });
    getOtpStatus.mockResolvedValue({ status: 'delivered', channel: 'sms' });
    verifyOtp.mockResolvedValue({ access_token: 'eva-jwt', user });
    const onLoginSuccess = vi.fn();
    render(<Login onLoginSuccess={onLoginSuccess} />);

    await userEvent.type(screen.getByLabelText('Phone number'), '9876543210');
    await userEvent.click(screen.getByRole('button', { name: 'Send verification code' }));
    expect(await screen.findByText(/Code delivered via SMS/)).toBeInTheDocument();
    expect(getOtpStatus).toHaveBeenCalledWith('otp-1');
    expect(sendOtp).toHaveBeenCalledWith('+919876543210');

    await userEvent.type(screen.getByLabelText('6-digit verification code'), '001234');
    await userEvent.click(screen.getByRole('button', { name: /Verify and continue/ }));
    await waitFor(() => expect(verifyOtp).toHaveBeenCalledWith('+919876543210', '001234'));
    expect(onLoginSuccess).toHaveBeenCalledWith(user, 'eva-jwt');
  });

  it('shows invalid or expired code feedback and supports resend and phone editing', async () => {
    sendOtp.mockResolvedValue({ message: 'sent' });
    getOtpStatus.mockResolvedValue({ status: 'queued', channel: null });
    verifyOtp.mockRejectedValue(new Error('Invalid or expired verification code'));
    render(<Login onLoginSuccess={vi.fn()} />);
    await userEvent.type(screen.getByLabelText('Phone number'), '9876543210');
    await userEvent.click(screen.getByRole('button', { name: 'Send verification code' }));
    await userEvent.type(screen.getByLabelText('6-digit verification code'), '111111');
    await userEvent.click(screen.getByRole('button', { name: /Verify and continue/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid or has expired/i);
    expect(screen.getByRole('button', { name: 'Resend code' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Resend code' })).toHaveTextContent(/Available in/);
    // The form indicates the cooldown and enables resend after its interval; avoid waiting 60 real seconds here.
    await userEvent.click(screen.getByRole('button', { name: /Edit phone number/ }));
    expect(screen.getByLabelText('Phone number')).toBeInTheDocument();
    return;
  });

  it('shows actionable guidance when MiniMoth reports delivery failure', async () => {
    sendOtp.mockResolvedValue({ message: 'accepted', otp_id: 'otp-failed' });
    getOtpStatus.mockResolvedValue({ status: 'failed', channel: 'sms' });
    render(<Login onLoginSuccess={vi.fn()} />);
    await userEvent.type(screen.getByLabelText('Phone number'), '9876543210');
    await userEvent.click(screen.getByRole('button', { name: 'Send verification code' }));
    expect(await screen.findByRole('status')).toHaveTextContent(/Dashboard → Usage → Failed deliveries/);
  });
});
