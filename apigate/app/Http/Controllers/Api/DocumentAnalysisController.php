<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Resources\DocumentAnalysisResource;
use App\Jobs\ProcessDocumentAnalysis;
use App\Models\Chat;
use App\Models\ChatDocument;
use App\Models\DocumentAnalysis;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Validation\Rule;

final class DocumentAnalysisController extends Controller
{
    public function analyze(Request $request, Chat $chat, ChatDocument $document): JsonResponse
    {
        $this->authorizeAccess($request, $chat, $document);

        $validated = $request->validate([
            'analysis_type'       => ['sometimes', 'string', Rule::in(array_keys(self::VALID_TYPES))],
            'compare_document_id' => ['sometimes', 'uuid', 'exists:chat_documents,id'],
            'force'               => ['sometimes', 'boolean'],
        ]);

        if (! $document->isReady()) {
            return response()->json([
                'error' => 'Document has not finished processing yet.',
                'code'  => 'DOCUMENT_NOT_READY',
            ], 422);
        }

        $type      = $validated['analysis_type'] ?? DocumentAnalysis::TYPE_FULL;
        $compareId = $validated['compare_document_id'] ?? null;
        $force     = filter_var($validated['force'] ?? false, FILTER_VALIDATE_BOOLEAN);

        if ($compareId) {
            $compareDoc = ChatDocument::find($compareId);
            if (! $compareDoc || $compareDoc->chat_id !== $chat->id) {
                return response()->json([
                    'error' => 'Compare document not found in this chat.',
                    'code'  => 'COMPARE_DOCUMENT_INVALID',
                ], 422);
            }
        }

        if (! $force) {
            $existing = DocumentAnalysis::where('chat_document_id', $document->id)
                ->ofType($type, $compareId)
                ->where('status', DocumentAnalysis::STATUS_DONE)
                ->latest()
                ->first();

            if ($existing) {
                return response()->json(DocumentAnalysisResource::make($existing));
            }
        }

        DocumentAnalysis::where('chat_document_id', $document->id)
            ->ofType($type, $compareId)
            ->whereIn('status', [
                DocumentAnalysis::STATUS_FAILED,
                DocumentAnalysis::STATUS_PENDING,
            ])
            ->delete();

        $analysis = DocumentAnalysis::create([
            'chat_document_id'    => $document->id,
            'user_id'             => $request->user()->id,
            'analysis_type'       => $type,
            'status'              => DocumentAnalysis::STATUS_PENDING,
            'compare_document_id' => $compareId,
        ]);

        ProcessDocumentAnalysis::dispatch(
            analysisId:        $analysis->id,
            documentId:        $document->id,
            analysisType:      $type,
            compareDocumentId: $compareId,
        )->onQueue('streaming');

        Log::info('[DocumentAnalysis] Dispatched', [
            'analysis_id' => $analysis->id,
            'document'    => $document->original_name,
            'type'        => $type,
            'user_id'     => $request->user()->id,
        ]);

        return response()->json(
            DocumentAnalysisResource::make($analysis),
            202,
        );
    }

    public function show(Request $request, Chat $chat, ChatDocument $document): JsonResponse
    {
        $this->authorizeAccess($request, $chat, $document);

        $validated = $request->validate([
            'analysis_type'       => ['sometimes', 'string', Rule::in(array_keys(self::VALID_TYPES))],
            'compare_document_id' => ['sometimes', 'uuid'],
        ]);

        $type      = $validated['analysis_type'] ?? DocumentAnalysis::TYPE_FULL;
        $compareId = $validated['compare_document_id'] ?? null;

        $analysis = DocumentAnalysis::where('chat_document_id', $document->id)
            ->ofType($type, $compareId)
            ->latest()
            ->first();

        if (! $analysis) {
            return response()->json(['status' => 'none'], 404);
        }

        return response()->json(DocumentAnalysisResource::make($analysis));
    }

    private function authorizeAccess(Request $request, Chat $chat, ?ChatDocument $document = null): void
    {
        abort_if($chat->user_id !== $request->user()->id, 403, 'Forbidden.');

        if ($document) {
            abort_if($document->chat_id !== $chat->id, 403, 'Document does not belong to this chat.');
        }
    }

    private const VALID_TYPES = [
        DocumentAnalysis::TYPE_FULL    => true,
        DocumentAnalysis::TYPE_RISK    => true,
        DocumentAnalysis::TYPE_CLAUSES => true,
        DocumentAnalysis::TYPE_COMPARE => true,
    ];
}
