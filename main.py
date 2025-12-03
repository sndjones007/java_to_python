import sys
import json
import os
import shutil
from pprint import pprint
from java_parser_javalang import JavaParser
from java_result_saver import JavaResultSaver
from method_doc_generator import MethodDocGenerator
from field_doc_generator import FieldDocGenerator
from code_generation_prompt_generator import CodeGenerationPromptGenerator
from env_config import EnvConfig


def cleanup_output_folders():
    """
    Clean up output folders before reexecution.
    """
    print("\n" + "="*60)
    print("🧹 Cleaning up old output files")
    print("="*60 + "\n")
    
    folders_to_clean = [
        EnvConfig.OUTPUT_JAVA_PARSED_FOLDER,
        EnvConfig.LLM_DOC_INPUT_FOLDER,
        EnvConfig.LLM_DOC_OUTPUT_FOLDER,
        EnvConfig.LLM_PYTHON_INPUT_FOLDER,
        EnvConfig.LLM_PYTHON_OUTPUT_FOLDER
    ]
    
    for folder in folders_to_clean:
        try:
            if os.path.exists(folder):
                shutil.rmtree(folder)
                print(f"   ✅ Cleaned: {folder}")
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            print(f"   ⚠️  Error cleaning {folder}: {str(e)}")
    
    print()


def main(java_file: str, output_dir: str = "java_json_output", cleanup: bool = True):
    """
    Main entry point: parse a Java file and generate Python code.
    
    Flow:
    1. Clean up old output files (optional)
    2. Parse Java file
    3. Save parsed results
    4. Generate LLM documentation input and output per method/field
    5. Generate Python code from documentation
    
    Args:
        java_file: Path to Java file to parse
        output_dir: Output directory for parsed results
        cleanup: If True, clean up old output files before starting
    """
    # Step 0: Cleanup old files
    if cleanup:
        cleanup_output_folders()
    
    # Step 1: Load Java source
    try:
        with open(java_file, "r", encoding="utf-8") as f:
            java_source = f.read()
    except FileNotFoundError:
        print(f"🚫 File not found: {java_file}")
        return

    # Step 2: Parse Java source
    print("="*60)
    print("🔍 STEP 1: Parsing Java File")
    print("="*60 + "\n")
    
    parser = JavaParser(java_source)
    results = parser.parse()

    if "error" in results:
        print(f"🚫 Parsing failed: {results['error']}")
        return
    
    # Extract source lines
    source_lines = java_source.split('\n')
    results['source_lines'] = source_lines
    
    print(f"✅ Java parsing complete\n")

    # Step 3: Save parsed results
    print("="*60)
    print("💾 STEP 2: Saving Parsed Results")
    print("="*60)
    
    saver = JavaResultSaver(output_dir=output_dir)
    saver.save_results(results, source_lines=source_lines)

    # Step 4: Generate LLM documentation input and output per method/field
    print("="*60)
    print("📋 STEP 3: Generating LLM Documentation per Method/Field")
    print("="*60 + "\n")
    
    #generate_llm_documentation(results, source_lines)

    # Step 5: Generate Python code from documentation
    print("="*60)
    print("🐍 STEP 4: Generating Python Code from Documentation")
    print("="*60 + "\n")
    
    generate_python_code()
    
    print("\n" + "="*60)
    print("✅ All steps completed!")
    print("="*60 + "\n")


def generate_llm_documentation(results: dict, source_lines: list):
    """
    Generate LLM documentation input and output per method and field.
    Creates individual JSON files for each method/field chunk in LLM_DOC_INPUT_FOLDER
    and LLM_DOC_OUTPUT_FOLDER. Methods and fields may be split into chunks.
    
    Args:
        results: Parsed Java results from JavaParser
        source_lines: List of source code lines
    """
    # Ensure output folders exist
    os.makedirs(EnvConfig.LLM_DOC_INPUT_FOLDER, exist_ok=True)
    os.makedirs(EnvConfig.LLM_DOC_OUTPUT_FOLDER, exist_ok=True)
    
    classes = results.get("classes", [])
    
    # ==================== PROCESS METHODS ====================
    print("📌 Processing Methods...")
    print("-" * 60)
    
    try:
        total_method_chunks = 0
        method_chunk_count = 0
        
        # Iterate through each class
        for class_idx, cls in enumerate(classes):
            class_name = cls.get("class_name", "Unknown")
            methods = cls.get("methods", [])
            
            if not methods:
                continue
            
            # Create generator for this class
            method_generator = MethodDocGenerator(results, source_lines)
            
            print(f"\n   Class: {class_name} ({len(methods)} methods)")
            
            # Process each method in the class
            for method_idx, method in enumerate(methods):
                try:
                    method_name = method.get("method_name", "unknown")
                    
                    print(f"      📄 Method {method_idx + 1}/{len(methods)}: {method_name}")
                    
                    # Build prompts for this specific method (returns array)
                    prompts = method_generator.build_prompts_for_method(class_idx, method_idx)
                    
                    if not prompts:
                        print(f"         ⚠️  No prompts generated for {method_name}")
                        continue
                    
                    # Handle both single prompt and array of prompts
                    if not isinstance(prompts, list):
                        prompts = [prompts]
                    
                    print(f"         📋 Generated {len(prompts)} prompt(s) for {method_name}")
                    
                    # Process each prompt chunk
                    for prompt_idx, prompt in enumerate(prompts):
                        total_method_chunks += 1
                        try:
                            # Create filename with chunk number if multiple chunks
                            if len(prompts) > 1:
                                chunk_suffix = f"_chunk{prompt_idx + 1}"
                            else:
                                chunk_suffix = ""
                            
                            # Save LLM input
                            llm_input_file = os.path.join(
                                EnvConfig.LLM_DOC_INPUT_FOLDER,
                                f"Method_{class_name}_{method_name}{chunk_suffix}_llm_input.json"
                            )
                            
                            llm_input_data = {
                                "class_name": class_name,
                                "class_idx": class_idx,
                                "method_name": method_name,
                                "method_idx": method_idx,
                                "chunk_idx": prompt_idx,
                                "total_chunks": len(prompts),
                                "method_details": method,
                                "prompt": prompt
                            }
                            
                            with open(llm_input_file, 'w', encoding='utf-8') as f:
                                json.dump(llm_input_data, f, indent=2)
                            
                            print(f"         ✅ LLM input saved (chunk {prompt_idx + 1}/{len(prompts)})")
                            
                            # Run LLM prompt and get output (returns MethodDoc object)
                            llm_output = method_generator.run_prompt(prompt)
                            
                            if not llm_output:
                                print(f"         ⚠️  No output from LLM for {method_name} chunk {prompt_idx + 1}")
                                continue
                            
                            # Convert MethodDoc to dict before serializing
                            llm_output_dict = llm_output.to_dict() if hasattr(llm_output, 'to_dict') else llm_output
                            
                            # Save LLM output
                            llm_output_file = os.path.join(
                                EnvConfig.LLM_DOC_OUTPUT_FOLDER,
                                f"Method_{class_name}_{method_name}{chunk_suffix}_llm_output.json"
                            )
                            
                            llm_output_data = {
                                "class_name": class_name,
                                "class_idx": class_idx,
                                "method_name": method_name,
                                "method_idx": method_idx,
                                "chunk_idx": prompt_idx,
                                "total_chunks": len(prompts),
                                "llm_output": llm_output_dict
                            }
                            
                            with open(llm_output_file, 'w', encoding='utf-8') as f:
                                json.dump(llm_output_data, f, indent=2)
                            
                            print(f"         ✅ LLM output saved (chunk {prompt_idx + 1}/{len(prompts)})")
                            method_chunk_count += 1
                            
                        except Exception as e:
                            print(f"         ❌ Error processing method {method_name} chunk {prompt_idx + 1}: {str(e)}")
                    
                except Exception as e:
                    print(f"      ❌ Error processing method {method_name}: {str(e)}")
        
        print(f"\n   ✅ Processed {method_chunk_count}/{total_method_chunks} method chunks successfully\n")
        
    except Exception as e:
        print(f"❌ Error processing methods: {str(e)}\n")

    # ==================== PROCESS FIELDS ====================
    print("\n📌 Processing Fields...")
    print("-" * 60)
    
    try:
        total_field_chunks = 0
        field_chunk_count = 0
        
        # Iterate through each class
        for class_idx, cls in enumerate(classes):
            class_name = cls.get("class_name", "Unknown")
            fields = cls.get("attributes", [])
            
            if not fields:
                continue
            
            # Create generator for this class
            field_generator = FieldDocGenerator(results, source_lines)
            
            print(f"\n   Class: {class_name} ({len(fields)} fields)")
            
            # Process each field in the class
            for field_idx, field in enumerate(fields):
                try:
                    field_name = field.get("name", "unknown")
                    
                    print(f"      📄 Field {field_idx + 1}/{len(fields)}: {field_name}")
                    
                    # Build prompts for this specific field (returns array)
                    prompts = field_generator.build_prompts_for_field(class_idx, field_idx)
                    
                    if not prompts:
                        print(f"         ⚠️  No prompts generated for {field_name}")
                        continue
                    
                    # Handle both single prompt and array of prompts
                    if not isinstance(prompts, list):
                        prompts = [prompts]
                    
                    print(f"         📋 Generated {len(prompts)} prompt(s) for {field_name}")
                    
                    # Process each prompt chunk
                    for prompt_idx, prompt in enumerate(prompts):
                        total_field_chunks += 1
                        try:
                            # Create filename with chunk number if multiple chunks
                            if len(prompts) > 1:
                                chunk_suffix = f"_chunk{prompt_idx + 1}"
                            else:
                                chunk_suffix = ""
                            
                            # Save LLM input
                            llm_input_file = os.path.join(
                                EnvConfig.LLM_DOC_INPUT_FOLDER,
                                f"Field_{class_name}_{field_name}{chunk_suffix}_llm_input.json"
                            )
                            
                            llm_input_data = {
                                "class_name": class_name,
                                "class_idx": class_idx,
                                "field_name": field_name,
                                "field_idx": field_idx,
                                "chunk_idx": prompt_idx,
                                "total_chunks": len(prompts),
                                "field_details": field,
                                "prompt": prompt
                            }
                            
                            with open(llm_input_file, 'w', encoding='utf-8') as f:
                                json.dump(llm_input_data, f, indent=2)
                            
                            print(f"         ✅ LLM input saved (chunk {prompt_idx + 1}/{len(prompts)})")
                            
                            # Run LLM prompt and get output (returns FieldDoc object)
                            llm_output = field_generator.run_prompt(prompt)
                            
                            if not llm_output:
                                print(f"         ⚠️  No output from LLM for {field_name} chunk {prompt_idx + 1}")
                                continue
                            
                            # Convert FieldDoc to dict before serializing
                            llm_output_dict = llm_output.to_dict() if hasattr(llm_output, 'to_dict') else llm_output
                            
                            # Save LLM output
                            llm_output_file = os.path.join(
                                EnvConfig.LLM_DOC_OUTPUT_FOLDER,
                                f"Field_{class_name}_{field_name}{chunk_suffix}_llm_output.json"
                            )
                            
                            llm_output_data = {
                                "class_name": class_name,
                                "class_idx": class_idx,
                                "field_name": field_name,
                                "field_idx": field_idx,
                                "chunk_idx": prompt_idx,
                                "total_chunks": len(prompts),
                                "llm_output": llm_output_dict
                            }
                            
                            with open(llm_output_file, 'w', encoding='utf-8') as f:
                                json.dump(llm_output_data, f, indent=2)
                            
                            print(f"         ✅ LLM output saved (chunk {prompt_idx + 1}/{len(prompts)})")
                            field_chunk_count += 1
                            
                        except Exception as e:
                            print(f"         ❌ Error processing field {field_name} chunk {prompt_idx + 1}: {str(e)}")
                    
                except Exception as e:
                    print(f"      ❌ Error processing field {field_name}: {str(e)}")
        
        print(f"\n   ✅ Processed {field_chunk_count}/{total_field_chunks} field chunks successfully\n")
        
    except Exception as e:
        print(f"❌ Error processing fields: {str(e)}\n")
    
    print("\n" + "="*60)
    print(f"✅ LLM documentation generated!")
    print("="*60)


def generate_python_code():
    """
    Generate Python code from documentation.
    
    Flow:
    1. Read LLM documentation output from LLM_DOC_OUTPUT_FOLDER
    2. Build Python code generation prompts using CodeGenerationPromptGenerator
    3. Run prompts through LLM to get Python code
    4. Save Python code to LLM_PYTHON_OUTPUT_FOLDER
    """
    print("\n")
    
    # Ensure output folders exist
    os.makedirs(EnvConfig.LLM_PYTHON_INPUT_FOLDER, exist_ok=True)
    os.makedirs(EnvConfig.LLM_PYTHON_OUTPUT_FOLDER, exist_ok=True)
    
    # Get all LLM documentation output files
    doc_files = [f for f in os.listdir(EnvConfig.LLM_DOC_OUTPUT_FOLDER) 
                 if f.endswith('_llm_output.json')]
    
    if not doc_files:
        print(f"🚫 No LLM documentation files found in {EnvConfig.LLM_DOC_OUTPUT_FOLDER}")
        return
    
    print(f"📁 Found {len(doc_files)} LLM documentation files\n")
    
    code_generator = CodeGenerationPromptGenerator()
    
    for doc_idx, doc_file in enumerate(doc_files):
        try:
            doc_file_path = os.path.join(EnvConfig.LLM_DOC_OUTPUT_FOLDER, doc_file)
            
            # Read documentation file
            with open(doc_file_path, 'r', encoding='utf-8') as f:
                doc_data = json.load(f)
            
            class_name = doc_data.get("class_name", "Unknown")
            method_or_field_name = doc_data.get("method_name") or doc_data.get("field_name", "unknown")
            doc_type = "Method" if "method_name" in doc_data else "Field"
            
            print(f"📄 {doc_idx + 1}/{len(doc_files)}: {doc_type} {class_name}.{method_or_field_name}")
            
            # Get the LLM output documentation
            llm_output = doc_data.get("llm_output", {})
            
            if not llm_output:
                print(f"   ⚠️  No LLM output found in {doc_file}")
                continue
            
            # Convert LLM output to JSON string for prompt building
            try:
                if isinstance(llm_output, dict):
                    documentation_json_string = json.dumps(llm_output, indent=2)
                else:
                    documentation_json_string = str(llm_output)
            except Exception as e:
                print(f"   ⚠️  Could not serialize LLM output: {str(e)}")
                continue
            
            # Build Python code generation prompt
            prompt = code_generator.build_prompt(documentation_json_string)
            
            if not prompt:
                print(f"   ⚠️  No prompt generated for {method_or_field_name}")
                continue
            
            # Save Python code generation input
            python_input_file = os.path.join(
                EnvConfig.LLM_PYTHON_INPUT_FOLDER,
                f"{doc_type}_{class_name}_{method_or_field_name}_python_input.json"
            )
            
            python_input_data = {
                "class_name": class_name,
                f"{doc_type.lower()}_name": method_or_field_name,
                "doc_type": doc_type,
                "documentation": llm_output,
                "prompt": prompt
            }
            
            with open(python_input_file, 'w', encoding='utf-8') as f:
                json.dump(python_input_data, f, indent=2)
            
            print(f"   ✅ Python code input prompt saved")
            
            # Run prompt through LLM to get Python code
            python_code_output = code_generator.run_prompt(prompt)
            
            if not python_code_output:
                print(f"   ⚠️  No Python code generated for {method_or_field_name}")
                continue
            
            # Convert to dict if it's an object
            python_code_dict = python_code_output.to_dict() if hasattr(python_code_output, 'to_dict') else python_code_output
            
            # Save Python code output
            python_output_file = os.path.join(
                EnvConfig.LLM_PYTHON_OUTPUT_FOLDER,
                f"{doc_type}_{class_name}_{method_or_field_name}_python_output.json"
            )
            
            python_output_data = {
                "class_name": class_name,
                f"{doc_type.lower()}_name": method_or_field_name,
                "doc_type": doc_type,
                "python_code": python_code_dict
            }
            
            with open(python_output_file, 'w', encoding='utf-8') as f:
                json.dump(python_output_data, f, indent=2)
            
            print(f"   ✅ Python code generated and saved\n")
            
        except Exception as e:
            print(f"   ❌ Error processing {doc_file}: {str(e)}\n")
    
    print("\n" + "="*60)
    print("✅ Python code generation complete!")
    print("="*60)


if __name__ == "__main__":
    java_file = EnvConfig.TEST_JAVA_FILE
    output_dir = EnvConfig.OUTPUT_JAVA_PARSED_FOLDER
    main(java_file, output_dir, cleanup=False)  # cleanup=True by default
