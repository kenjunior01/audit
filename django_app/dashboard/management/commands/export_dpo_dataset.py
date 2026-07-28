
import json
from django.core.management.base import BaseCommand
from dashboard.models import AiFeedback

class Command(BaseCommand):
    help = 'Exports AI feedback data to JSONL format for DPO training'

    def add_arguments(self, parser):
        parser.add_argument('--output', type=str, default='dpo_dataset.jsonl', help='Output file path')

    def handle(self, *args, **options):
        output_file = options['output']
        # Filter for feedback that contains corrections (inaccurate feedback)
        # We assume 'inaccurate' means the user provided a correction.
        # We also check if human_correction is populated.
        feedbacks = AiFeedback.objects.filter(
            feedback_type='inaccurate',
            human_correction__isnull=False
        ).exclude(human_correction={})
        
        count = 0
        with open(output_file, 'w', encoding='utf-8') as f:
            for fb in feedbacks:
                # Ensure we have the necessary components
                if not fb.input_context or not fb.ai_response:
                    continue
                
                # Format for DPO (Unsloth/TRL standard)
                # Prompt: System + User Input
                # Chosen: Human Correction
                # Rejected: AI Response
                
                # Serialize if they are JSON objects
                prompt_content = json.dumps(fb.input_context) if isinstance(fb.input_context, (dict, list)) else str(fb.input_context)
                chosen_content = json.dumps(fb.human_correction) if isinstance(fb.human_correction, (dict, list)) else str(fb.human_correction)
                rejected_content = json.dumps(fb.ai_response) if isinstance(fb.ai_response, (dict, list)) else str(fb.ai_response)

                entry = {
                    "prompt": f"<system>You are an expert audit assistant. Analyze the transaction for risks.</system>\n<user>{prompt_content}</user>",
                    "chosen": chosen_content,
                    "rejected": rejected_content
                }
                
                f.write(json.dumps(entry) + '\n')
                count += 1
                
        self.stdout.write(self.style.SUCCESS(f'Successfully exported {count} DPO training samples to {output_file}'))
