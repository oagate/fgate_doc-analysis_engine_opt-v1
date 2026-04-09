<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * @property string      $id
 * @property string      $chat_document_id
 * @property string      $user_id
 * @property string      $analysis_type       full|risk|clauses|compare
 * @property string      $status              pending|processing|done|failed
 * @property int|null    $risk_score          0–100
 * @property string|null $risk_label
 * @property array|null  $highlights
 * @property array|null  $compare_highlights
 * @property array|null  $metrics
 * @property string|null $compare_summary
 * @property string|null $error_message
 * @property string|null $compare_document_id
 */
final class DocumentAnalysis extends Model
{
    use HasUuids;

    public $incrementing = false;
    protected $keyType   = 'string';
    public const STATUS_PENDING    = 'pending';
    public const STATUS_PROCESSING = 'processing';
    public const STATUS_DONE       = 'done';
    public const STATUS_FAILED     = 'failed';
    public const TYPE_FULL    = 'full';
    public const TYPE_RISK    = 'risk';
    public const TYPE_CLAUSES = 'clauses';
    public const TYPE_COMPARE = 'compare';

    protected $fillable = [
        'chat_document_id',
        'user_id',
        'analysis_type',
        'status',
        'risk_score',
        'risk_label',
        'highlights',
        'compare_highlights',
        'metrics',
        'compare_summary',
        'error_message',
        'compare_document_id',
    ];

    protected $casts = [
        'highlights'         => 'array',
        'compare_highlights' => 'array',
        'metrics'            => 'array',
        'risk_score'         => 'integer',
    ];

    public function document(): BelongsTo
    {
        return $this->belongsTo(ChatDocument::class, 'chat_document_id');
    }

    public function compareDocument(): BelongsTo
    {
        return $this->belongsTo(ChatDocument::class, 'compare_document_id');
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function isDone(): bool
    {
        return $this->status === self::STATUS_DONE;
    }

    public function isFailed(): bool
    {
        return $this->status === self::STATUS_FAILED;
    }

    public function isPending(): bool
    {
        return $this->status === self::STATUS_PENDING;
    }

    public function isProcessing(): bool
    {
        return in_array($this->status, [self::STATUS_PENDING, self::STATUS_PROCESSING], true);
    }

    public function scopeOfType($query, string $type, ?string $compareDocumentId = null)
    {
        return $query
            ->where('analysis_type', $type)
            ->when(
                $compareDocumentId,
                fn ($q) => $q->where('compare_document_id', $compareDocumentId),
                fn ($q) => $q->whereNull('compare_document_id'),
            );
    }

    public function scopeTerminal($query)
    {
        return $query->whereIn('status', [self::STATUS_DONE, self::STATUS_FAILED]);
    }
}
