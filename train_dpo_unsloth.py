from unsloth import FastLanguageModel, PatchDPOTrainer
from unsloth import is_bfloat16_supported
from trl import DPOTrainer, DPOConfig
from transformers import TrainingArguments
from datasets import load_dataset
import torch

# 1. Configuration
max_seq_length = 2048
dtype = None # None for auto detection. Float16 for Tesla T4, V100, Bfloat16 for Ampere+
load_in_4bit = True # Use 4bit quantization to reduce memory usage. Can be False.

model_name = "unsloth/DeepSeek-R1-Distill-Llama-8B"
output_dir = "fine_tuned_model"
dataset_path = "dpo_dataset.jsonl" # Path to the file exported by 'python manage.py export_dpo_dataset'

def train():
    print(f"Loading model: {model_name}...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name = model_name,
        max_seq_length = max_seq_length,
        dtype = dtype,
        load_in_4bit = load_in_4bit,
    )

    # 2. Add LoRA adapters
    model = FastLanguageModel.get_peft_model(
        model,
        r = 16, # Choose any number > 0 ! Suggested 8, 16, 32, 64, 128
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                          "gate_proj", "up_proj", "down_proj",],
        lora_alpha = 16,
        lora_dropout = 0, # Supports any, but = 0 is optimized
        bias = "none",    # Supports any, but = "none" is optimized
        use_gradient_checkpointing = "unsloth", # True or "unsloth" for very long context
        random_state = 3407,
        use_rslora = False,  # We support rank stabilized LoRA
        loftq_config = None, # And LoftQ
    )

    # 3. Load Dataset
    print(f"Loading dataset from {dataset_path}...")
    # Expecting JSONL with fields: "prompt", "chosen", "rejected"
    dataset = load_dataset("json", data_files=dataset_path, split="train")

    # 4. Initialize DPO Trainer
    PatchDPOTrainer() # Patch to make DPO 2x faster
    
    training_args = DPOConfig(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_ratio = 0.1,
        num_train_epochs = 3,
        learning_rate = 5e-6,
        fp16 = not is_bfloat16_supported(),
        bf16 = is_bfloat16_supported(),
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 42,
        output_dir = output_dir,
    )

    trainer = DPOTrainer(
        model = model,
        ref_model = None, # Unsloth handles this efficiently
        tokenizer = tokenizer,
        beta = 0.1,
        train_dataset = dataset,
        args = training_args,
        max_length = max_seq_length,
        max_prompt_length = max_seq_length // 2,
        max_target_length = max_seq_length // 2,
    )

    # 5. Train
    print("Starting training...")
    trainer.train()

    # 6. Save
    print(f"Saving model to {output_dir}...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    
    # Save GGUF for Ollama
    # model.save_pretrained_gguf(output_dir, tokenizer, quantization_method = "q4_k_m")

if __name__ == "__main__":
    train()
