import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return {
    ...actual,
    api: { files: { list: vi.fn(), getContent: vi.fn(), upload: vi.fn() } },
  };
});

import { api, ApiError, setAuthToken } from '../src/api/client';
import { FilesViewer, MAX_UPLOAD_BYTES } from '../src/pages/FilesViewer';

const files = api.files as unknown as Record<string, ReturnType<typeof vi.fn>>;
const row = (name: string) => ({ path: name, name, size: 3, is_directory: false, modified_at: '' });
const pick = (f: File) => userEvent.upload(screen.getByLabelText('Choose a file to upload'), f);

beforeEach(() => {
  vi.clearAllMocks();
  files.list.mockResolvedValue([]);
  files.getContent.mockResolvedValue({ path: 'x', content: 'hello' });
});

describe('Files page upload', () => {
  it('uploads into the current folder, refreshes the list and selects the new file', async () => {
    files.upload.mockResolvedValue({ path: 'notes.txt', size: 5 });
    files.list.mockResolvedValueOnce([]).mockResolvedValue([row('notes.txt')]);
    render(<FilesViewer />);
    await screen.findByText('This folder is empty.');

    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' });
    await pick(file);

    expect(files.upload).toHaveBeenCalledWith('', file);
    expect(await screen.findByRole('status')).toHaveTextContent('Uploaded notes.txt (5 B)');
    await waitFor(() => expect(files.getContent).toHaveBeenCalledWith('notes.txt'));
    expect(await screen.findByText('hello')).toBeInTheDocument();
  });

  it('rejects oversize files client-side without calling the API', async () => {
    render(<FilesViewer />);
    await screen.findByText('This folder is empty.');
    await pick(new File([new Uint8Array(MAX_UPLOAD_BYTES + 1)], 'big.bin'));
    expect(await screen.findByRole('alert')).toHaveTextContent('larger than');
    expect(files.upload).not.toHaveBeenCalled();
  });

  it.each([
    [404, 'does not support uploads yet'],
    [405, 'does not support uploads yet'],
    [409, 'already exists'],
    [413, 'Workspace quota exceeded'],
    [503, 'audit log is unavailable'],
  ])('maps HTTP %i to a clear message', async (status, text) => {
    files.upload.mockRejectedValue(new ApiError('Workspace quota exceeded', status));
    render(<FilesViewer />);
    await screen.findByText('This folder is empty.');
    await pick(new File(['a'], 'a.txt'));
    expect(await screen.findByRole('alert')).toHaveTextContent(text);
  });

  it('shows other backend errors verbatim', async () => {
    files.upload.mockRejectedValue(new ApiError('Disk full', 500));
    render(<FilesViewer />);
    await screen.findByText('This folder is empty.');
    await pick(new File(['a'], 'a.txt'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Disk full');
  });
});

describe('client.files.upload', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    setAuthToken(null);
  });

  it('posts multipart form data with the bearer token and no forced JSON content-type', async () => {
    const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
    actual.setAuthToken('tok');
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify({ path: 'a/x.txt', size: 1 }), { status: 201 }));
    vi.stubGlobal('fetch', f);

    const out = await actual.api.files.upload('a b', new File(['x'], 'x.txt'));

    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/api/files/upload?path=a%20b');
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get('file')).toBeInstanceOf(File);
    const h = new Headers(init.headers);
    expect(h.get('Authorization')).toBe('Bearer tok');
    expect(h.get('Content-Type')).toBeNull();
    expect(out).toEqual({ path: 'a/x.txt', size: 1 });
  });
});
