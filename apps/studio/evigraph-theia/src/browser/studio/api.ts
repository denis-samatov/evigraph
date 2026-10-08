/** Client for the EviGraph Core HTTP API. */

export const API_URL_KEY = 'evigraph.apiUrl';
export const DEFAULT_API_URL = 'http://127.0.0.1:8000';

export function apiUrl(): string {
    try {
        return window.localStorage.getItem(API_URL_KEY) || DEFAULT_API_URL;
    } catch {
        return DEFAULT_API_URL;
    }
}

export function setApiUrl(url: string): void {
    window.localStorage.setItem(API_URL_KEY, url.replace(/\/+$/, ''));
}

export interface Project { id: string; name: string }
export interface CatalogSummary { id: string; name: string; versions: { id: string; version: number; status: string }[] }
export interface DocumentSummary {
    document_id: string;
    version_id: string;
    version: number;
    title: string | null;
    chars: number;
    provenance_group_id: string;
    provenance_reason: string;
    group_size: number;
}
export interface ReviewRow {
    assertion_id: string;
    concept_id: string;
    concept_key: string;
    concept_label: string;
    state: 'proposed' | 'accepted' | 'rejected' | 'auto_applied';
    revision: number;
    score: number | null;
    rank: number | null;
    decision: 'auto_applied' | 'needs_review' | null;
}
export interface ReviewView {
    document_version_id: string;
    catalog_version_id: string;
    release_id: string | null;
    certification: { id: string; alpha: number; delta: number; tau: number | null } | null;
    completed: boolean;
    assertions: ReviewRow[];
}
export interface EvidenceSpan {
    id: string;
    start: number;
    end: number;
    quote: string;
    score: number;
    rank: number;
    method: string;
    deletion_drop: number | null;
}
export interface Concept { id: string; key: string; label: string; definition: string | null }

export class ApiError extends Error {
    constructor(readonly status: number, message: string) {
        super(message);
    }
}

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown, query?: Record<string, string | number>): Promise<T> {
    const url = new URL(path, apiUrl());
    Object.entries(query ?? {}).forEach(([k, v]) => url.searchParams.set(k, String(v)));
    const response = await fetch(url.toString(), {
        method,
        headers: body === undefined ? undefined : { 'content-type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body)
    });
    if (!response.ok) {
        let detail = response.statusText;
        try {
            const json = await response.json();
            detail = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail);
        } catch {
            // keep status text
        }
        throw new ApiError(response.status, `${response.status}: ${detail}`);
    }
    return (await response.json()) as T;
}

const key = (): string => (crypto as Crypto & { randomUUID(): string }).randomUUID();

export const api = {
    projects: () => call<Project[]>('GET', '/projects'),
    catalogs: (projectId: string) => call<CatalogSummary[]>('GET', `/projects/${projectId}/catalogs`),
    concepts: (catalogVersionId: string) =>
        call<{ concepts: Concept[] }>('GET', `/catalog-versions/${catalogVersionId}`).then(v => v.concepts),
    documents: (projectId: string, offset = 0) =>
        call<DocumentSummary[]>('GET', `/projects/${projectId}/documents`, undefined, { limit: 200, offset }),
    text: (versionId: string) => call<{ text: string }>('GET', `/document-versions/${versionId}/text`).then(t => t.text),
    review: (versionId: string, catalogVersionId: string) =>
        call<ReviewView>('GET', `/document-versions/${versionId}/review`, undefined, { catalog_version_id: catalogVersionId }),
    suggest: (versionId: string, catalogVersionId: string, topK = 8) =>
        call<unknown>('POST', `/document-versions/${versionId}/suggestions`, { catalog_version_id: catalogVersionId, top_k: topK }),
    evidence: (assertionId: string) =>
        call<{ spans: EvidenceSpan[] }>('GET', `/assertions/${assertionId}/evidence`).then(e => e.spans),
    review_: (assertionId: string, kind: 'accept' | 'reject' | 'withdraw', expectedRevision: number, reviewer: string) =>
        call<unknown>('POST', `/assertions/${assertionId}/review`, {
            kind,
            expected_revision: expectedRevision,
            idempotency_key: key(),
            reviewer
        }),
    add: (versionId: string, conceptId: string, reviewer: string) =>
        call<unknown>('POST', `/document-versions/${versionId}/assertions`, { concept_id: conceptId, idempotency_key: key(), reviewer }),
    complete: (versionId: string, catalogVersionId: string, reviewer: string) =>
        call<unknown>('POST', `/document-versions/${versionId}/review-completions`, {
            catalog_version_id: catalogVersionId,
            idempotency_key: key(),
            reviewer
        })
};

/**
 * Core reports offsets in Unicode code points; JavaScript strings index UTF-16 code units.
 * Returns the UTF-16 index of every code point boundary (length = code points + 1).
 */
export function codePointToUtf16(text: string): number[] {
    const out = [0];
    let i = 0;
    for (const ch of text) {
        i += ch.length;
        out.push(i);
    }
    return out;
}
