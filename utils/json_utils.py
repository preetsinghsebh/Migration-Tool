import json
import logging

logger = logging.getLogger(__name__)

def write_json_iteratively(file_path, generator):
    """
    Writes items from a generator into a JSON array iteratively to save memory.
    
    Args:
        file_path (str): The path to the output JSON file.
        generator (iterable): An iterable/generator that yields dictionary objects.
    """
    logger.info(f"Starting iterative JSON export to {file_path}")
    
    count = 0
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('[\n')
        
        first = True
        for item in generator:
            if not first:
                f.write(',\n')
            
            # Serialize the item and indent it for readability (optional, but good for structure)
            json_str = json.dumps(item, indent=2)
            
            # Indent each line of the serialized string so it looks good inside the array
            indented_str = '\n'.join('  ' + line for line in json_str.splitlines())
            f.write(indented_str)
            
            first = False
            count += 1
            
            if count % 100 == 0:
                logger.info(f"Exported {count} items...")
                
        f.write('\n]\n')
        
    logger.info(f"Finished iterative JSON export. Total items: {count}")
    return count
