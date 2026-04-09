<?php

declare(strict_types=1);

use App\Http\Controllers\Api\DocumentAnalysisController;
use Illuminate\Support\Facades\Route;

Route::middleware(['auth:sanctum', 'throttle:60,1'])->group(function () {
    Route::prefix('chats/{chat}/documents/{document}')->group(function () {
        Route::post('analyze', [DocumentAnalysisController::class, 'analyze'])
            ->name('documents.analysis.trigger');
        Route::get('analysis', [DocumentAnalysisController::class, 'show'])
            ->name('documents.analysis.show');
    });
});
