<?php

declare(strict_types=1);

namespace App\Jobs;

use App\Models\ChatDocument;
use App\Models\DocumentAnalysis;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Throwable;

final class ProcessDocumentAnalysis implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $tries   = 2;
    public int $timeout = 120;

    public function __construct(
        private readonly string  $analysisId,
        private readonly string  $documentId,
        private readonly string  $analysisType,
        private readonly ?string $compareDocumentId = null,
    ) {}

    public function handle(): void
    {
        $analysis = DocumentAnalysis::find($this->analysisId);

        if (! $analysis) {
            Log::warning('[ProcessDocumentAnalysis] Analysis record not found', [
                'analysis_id' => $this->analysisId,
            ]);
            return;
        }

        $document = ChatDocument::find($this->documentId);

        if (! $document || ! $document->isReady()) {
            $this->markFailed($analysis, 'Document is not ready for analysis.');
            return;
        }

        $analysis->update(['status' => DocumentAnalysis::STATUS_PROCESSING]);

        $payload = $this->buildPayload($document);

        try {
            $response = $this->callKernel($payload);
            $this->writeResult($analysis, $response->json());

            Log::info('[ProcessDocumentAnalysis] Done', [
                'analysis_id' => $this->analysisId,
                'type'        => $this->analysisType,
                'highlights'  => count($response->json('highlights', [])),
                'risk_score'  => $response->json('metrics.risk_score'),
            ]);
        } catch (Throwable $e) {
            Log::error('[ProcessDocumentAnalysis] Failed', [
                'analysis_id' => $this->analysisId,
                'attempt'     => $this->attempts(),
                'error'       => $e->getMessage(),
            ]);

            if ($this->attempts() >= $this->tries) {
                $this->markFailed($analysis, $e->getMessage());
            } else {
                throw $e;
            }
        }
    }

    private function buildPayload(ChatDocument $document): array
    {
        $payload = [
            'document_id'   => $this->documentId,
            'filename'      => $document->original_name,
            'text'          => $document->extracted_text,
            'analysis_type' => $this->analysisType,
        ];

        if ($this->compareDocumentId) {
            $compareDoc = ChatDocument::find($this->compareDocumentId);

            if ($compareDoc && $compareDoc->isReady()) {
                $payload['compare_text']     = $compareDoc->extracted_text;
                $payload['compare_filename'] = $compareDoc->original_name;
            }
        }

        return $payload;
    }

    private function callKernel(array $payload): \Illuminate\Http\Client\Response
    {
        $kernelUrl = rtrim(config('services.kernel.url', 'http://127.0.0.1:9002'), '/');
        $secret    = config('services.kernel.secret', '');

        $response = Http::timeout(110)
            ->withHeaders(['X-Kernel-Secret' => $secret])
            ->post("{$kernelUrl}/analyze-document", $payload);

        if (! $response->successful()) {
            throw new \RuntimeException(
                "Kernel returned HTTP {$response->status()}: " . $response->body()
            );
        }

        return $response;
    }

    private function writeResult(DocumentAnalysis $analysis, array $data): void
    {
        $analysis->update([
            'status'             => DocumentAnalysis::STATUS_DONE,
            'risk_score'         => $data['metrics']['risk_score'] ?? null,
            'risk_label'         => $data['metrics']['risk_label'] ?? null,
            'highlights'         => $data['highlights']         ?? [],
            'compare_highlights' => $data['compare_highlights'] ?? null,
            'metrics'            => $data['metrics']            ?? [],
            'compare_summary'    => $data['compare_summary']    ?? null,
            'error_message'      => null,
        ]);
    }

    private function markFailed(DocumentAnalysis $analysis, string $reason): void
    {
        $analysis->update([
            'status'        => DocumentAnalysis::STATUS_FAILED,
            'error_message' => $reason,
        ]);
    }
}
