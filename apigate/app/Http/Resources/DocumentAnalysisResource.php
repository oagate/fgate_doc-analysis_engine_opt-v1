<?php

declare(strict_types=1);

namespace App\Http\Resources;

use App\Models\DocumentAnalysis;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;


final class DocumentAnalysisResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id'                 => $this->id,
            'status'             => $this->status,
            'analysis_type'      => $this->analysis_type,
            'risk_score'         => $this->risk_score,
            'risk_label'         => $this->risk_label,
            'highlights'         => $this->highlights ?? [],
            'compare_highlights' => $this->compare_highlights,
            'metrics'            => $this->metrics ?? [],
            'compare_summary'    => $this->compare_summary,
            'error_message' => $this->isFailed() ? $this->error_message : null,
            'created_at' => $this->created_at?->toISOString(),
            'updated_at' => $this->updated_at?->toISOString(),
        ];
    }
}
