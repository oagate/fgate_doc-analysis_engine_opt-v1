<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('document_analyses', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('chat_document_id')
                ->constrained('chat_documents')
                ->cascadeOnDelete();

            $table->foreignUuid('compare_document_id')
                ->nullable()
                ->constrained('chat_documents')
                ->nullOnDelete();

            $table->foreignUuid('user_id')
                ->constrained('users')
                ->cascadeOnDelete();
            
            $table->string('analysis_type', 20)->default('full'); // full,risk,clauses, compare
            $table->string('status', 20)->default('pending'); // pending,processing,done,failed
            $table->unsignedSmallInteger('risk_score')->nullable(); // 0–100
            $table->string('risk_label', 30)->nullable(); // Low, Medium,High,Critical
            $table->json('highlights')->nullable();
            $table->json('compare_highlights')->nullable();
            $table->json('metrics')->nullable();           
            $table->text('compare_summary')->nullable();   
            $table->text('error_message')->nullable();     
            $table->timestamps();
            $table->index(['chat_document_id', 'status'], 'da_doc_status');
            $table->index(
                ['chat_document_id', 'analysis_type', 'compare_document_id'],
                'da_doc_type_compare',
            );

            $table->index(['user_id', 'created_at'], 'da_user_created');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('document_analyses');
    }
};
